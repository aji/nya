import urllib
import time
import traceback
import json
import string

def diff(fr, to):
    def diff_lcs(memo, fr, i, to, j):
        def lcs():
            if j == 0:
                return 0, [('-', x) for x in fr[:i]]
            if i == 0:
                return 0, [('+', x) for x in to[:j]]

            if fr[i-1] == to[j-1]:
                n, s = diff_lcs(memo, fr, i-1, to, j-1)
                return n + 1, s + [(' ', fr[i-1])]

            nfr, sfr = diff_lcs(memo, fr, i-1, to, j)
            nto, sto = diff_lcs(memo, fr, i, to, j-1)

            if nfr >= nto:
                return nfr, sfr + [('-', fr[i-1])]
            else:
                return nto, sto + [('+', to[j-1])]

        if (i, j) not in memo:
            memo[(i, j)] = lcs()
        return memo[(i, j)]

    n, s = diff_lcs({}, fr, len(fr), to, len(to))
    return s

def normalize(word):
    return ''.join(x for x in word.lower() if x not in string.punctuation)

CONFPATH = 'nya.json'
ON_CONF_CHANGED = []

CONF = {
    'users': [
        ],
    }

def load_conf():
    global CONF

    try:
        with open(CONFPATH, 'r') as f:
            CONF = json.load(f)
    except IOError:
        pass

    conf_changed()

def save_conf():
    try:
        with open(CONFPATH, 'w') as f:
            json.dump(CONF, f)
    except Exception:
        traceback.print_exc()

def conf_changed():
    for cb in ON_CONF_CHANGED:
        cb()

import weechat

OPTIONS = {
    'lastfm.root':   'http://ws.audioscrobbler.com/2.0/',
    'lastfm.key':    '',

    'youtube.root':  'https://www.googleapis.com/youtube/v3/',
    'youtube.key':   '',
    }

def option(name):
    return lambda: weechat.config_get_plugin(name)

ALERT_COUNT = 0
def alert(msg, limit=None):
    global ALERT_COUNT
    weechat.prnt('', 'ALERT: ' + msg)
    if limit is None:
        ALERT_COUNT = 0
    else:
        ALERT_COUNT += 1
        if ALERT_COUNT == limit + 1:
            msg = '(... output truncated, see weechat buffer ...)'
        elif ALERT_COUNT > limit:
            return
    cmd = '/msg @{} \0030,4 {} \003'
    used = set()
    for u in ALL_USERS:
        for bufname in u.buffers:
            if bufname in used:
                continue
            used.add(bufname)
            try:
                chan = bufname.split(',')[-1]
                buf = weechat.info_get('irc_buffer', bufname)
                if not buf:
                    continue
                weechat.command(buf, cmd.format(chan, msg))
            except IndexError:
                pass

LOGLEVELS = ['info', 'debug', 'trace']
LOGLEVEL = 1
def log(msg, level=0):
    if level > LOGLEVEL:
        return
    cmd = '/msg @{} \00302{}\003'
    used = set()
    for u in ALL_USERS:
        for bufname in u.buffers:
            if bufname in used:
                continue
            used.add(bufname)
            try:
                chan = bufname.split(',')[-1]
                buf = weechat.info_get('irc_buffer', bufname)
                if not buf:
                    continue
                weechat.command(buf, cmd.format(chan, msg))
            except:
                pass
def log_set_level(level):
    global LOGLEVEL
    try:
        LOGLEVEL = LOGLEVELS.index(level.lower())
        return True
    except:
        return False
INFO = lambda s: log(s, 0)
DEBUG = lambda s: log(s, 1)
TRACE = lambda s: log(s, 2)

def trace_repr(xs, group=5, fn=TRACE):
    for i in range(0, len(xs), group):
        fn('   ' + ' '.join(repr(x) for x in xs[i:i+group]))

LASTFM_API_ROOT  = option('lastfm.root')
LASTFM_API_KEY   = option('lastfm.key')
YOUTUBE_API_ROOT = option('youtube.root')
YOUTUBE_API_KEY  = option('youtube.key')

def lastfm_url(method, **params):
    pre = '?method={}&format={}&api_key={}'.format(method, 'json', LASTFM_API_KEY())
    extra = ''
    if len(params) > 0:
        extra = '&' + urllib.urlencode(params)
    return LASTFM_API_ROOT() + '{}{}'.format(pre, extra)

def youtube_url(method, **params):
    q = { 'key': YOUTUBE_API_KEY() }
    q.update(params)
    return YOUTUBE_API_ROOT() + method + '?' + urllib.urlencode(q)

def detext(s):
    if s is not None and '#text' in s:
        return s['#text']
    return s

URL_REQUEST_TMP = {}
URL_REQUEST_LAST = 0
def url_finished(cb, command, rc, out, err):
    URL_REQUEST_TMP[cb]['data'] += out
    if rc < 0:
        return weechat.WEECHAT_RC_OK
    try:
        URL_REQUEST_TMP[cb]['cb'](URL_REQUEST_TMP[cb]['data'])
    except Exception as e:
        weechat.prnt('', u'  !! {}'.format(str(e)))
        for ln in traceback.format_exc().split('\n'):
            weechat.prnt('', ln)
        alert('Exception when handling ' + URL_REQUEST_TMP[cb]['url'])
        alert('  ' + repr(e))
    del URL_REQUEST_TMP[cb]
    return weechat.WEECHAT_RC_OK
def get_data(url, cb):
    global URL_REQUEST_LAST
    URL_REQUEST_LAST += 1
    k = str(URL_REQUEST_LAST)
    URL_REQUEST_TMP[k] = {'cb':cb, 'url':url, 'data':''}
    weechat.prnt('', 'fetch: {}'.format(url))
    weechat.hook_process('url:{}'.format(url), 5*1000, 'url_finished', k)

def get_json(url, on_complete):
    def x(d):
        try:
            j = json.loads(d, 'utf-8')
        except ValueError as e:
            alert('json.loads error: ' + repr(e))
            raise e
        on_complete(j)
    get_data(url, x)

class Track(object):
    def __init__(self, kw):
        self.url          = detext(kw.get(u'url',         None))
        self.date         = detext(kw.get(u'date',        None))
        self.artist       = detext(kw.get(u'artist',      None))
        self.name         = detext(kw.get(u'name',        None))

        self.attrs        = kw.get('@attr', {})

        self.now_playing  = self.attrs.get(u'nowplaying') == u'true'

    def __repr__(self):
        return 'Track({} by {})'.format(repr(self.name), repr(self.artist))

    def __eq__(self, other):
        #if self.date is not None and other.date is not None:
        #    if self.date != other.date:
        #        return False

        if normalize(self.name) != normalize(other.name):
            return False

        if normalize(self.artist) != normalize(other.artist):
            return False

        return True

    def __ne__(self, other):
        return not (self == other)

class User(object):
    def __init__(self, lastfm_name, buffers):
        self.lastfm_name  = lastfm_name
        self.buffers      = buffers

        self.last_tracks  = []
        self.newest       = []

    def __repr__(self):
        return 'User({})'.format(repr(self.lastfm_name))


def get_tracks(u, on_complete):
    def x(d):
        if u'recenttracks' not in d or u'track' not in d[u'recenttracks']:
            on_complete(False, d, u)
        tracks = []
        for t in d[u'recenttracks'][u'track']:
            tracks.append(Track(t))
        on_complete(True, tracks, u)
    if not LASTFM_API_KEY():
        on_complete(False, {u'error': '-1', u'message': 'no lastfm key'}, u)
        return
    try:
        TRACE('checking tracks for {}'.format(u.lastfm_name))
        get_json(
            lastfm_url(
                'user.getRecentTracks',
                user=u.lastfm_name,
                limit='20'
                ),
            x
            )
    except Exception as e:
        alert('exception when getting recent tracks:')
        alert('  {}'.format(repr(e)))
        for ln in traceback.format_exc().split('\n'):
            weechat.prnt('', ln)

def get_video(track, on_complete):
    def x(d):
        if u'kind' not in d or d[u'kind'] != u'youtube#searchListResponse':
            on_complete(track, None)
            return
        if len(d[u'items']) == 0:
            on_complete(track, None)
            return
        first = d[u'items'][0]
        if u'kind' not in first or first[u'kind'] != u'youtube#searchResult':
            on_complete(track, None)
            return
        vid = first[u'id']
        if u'kind' not in vid or vid[u'kind'] != u'youtube#video':
            on_complete(track, None)
            return
        on_complete(track, vid[u'videoId'])
    if not YOUTUBE_API_KEY():
        on_complete(track, None)
        return
    try:
        get_json(youtube_url(u'search', part=u'snippet',
                    q=u'{} {}'.format(track.artist, track.name).encode('utf-8'),
                    maxResults=1,
                    type=u'video'), x)
    except Exception:
        on_complete(track, None)

def do_poll(u, on_complete):
    def request_completed(ok, tracks, u):
        if not ok:
            alert(u'  !! {}: #{}: {}'.format(
                  repr(u), tracks[u'error'], tracks[u'message']))
            return

        if len(u.last_tracks) == 0:
            u.last_tracks = tracks[:]
            return

        added = [t for op, t in diff(u.last_tracks[:], tracks[:]) if op == '+']
        u.newest = added + u.newest
        u.last_tracks = tracks[:]

        on_complete(u)

    get_tracks(u, request_completed)

def on_one_fire(data, remaining):
    def on_complete(u):
        def get_next_video():
            if len(u.newest) == 0:
                return
            get_video(u.newest[-1], got_video_id)
            u.newest = u.newest[:-1]
        def got_video_id(t, vid):
            msg = ('/say \0033{} {} to "{}" by {}{}'
                .format(
                    u.lastfm_name,
                    'now listening' if t.now_playing else 'listened',
                    t.name.encode('utf-8'),
                    t.artist.encode('utf-8'),
                    (u'' if vid is None else u': http://youtu.be/{}'
                        .format(vid)
                        .encode('utf-8')
                        )
                    )
                )
            for b in u.buffers:
                buf = weechat.info_get('irc_buffer', b)
                if buf:
                    weechat.command(buf, msg)
            get_next_video()
        get_next_video()
    if int(remaining) < len(ALL_USERS):
        u = ALL_USERS[int(remaining)]
        do_poll(u, on_complete)
    return weechat.WEECHAT_RC_OK

def on_timer_fire(data, remaining):
    if not LASTFM_API_KEY():
        alert('!!!! no lastfm key set')
        return weechat.WEECHAT_RC_ERROR
    if not YOUTUBE_API_KEY():
        alert('warning: no youtube key')
    if len(ALL_USERS) > 0:
        weechat.hook_timer(1900, 0, len(ALL_USERS), 'on_one_fire', '')
    weechat.hook_timer((max(len(ALL_USERS), 5) + 2) * 2000,
                       0, 1, 'on_timer_fire', '')
    return weechat.WEECHAT_RC_OK

ALL_USERS = []
USERS_BY_LASTFM = {}
def initialize_users():
    global ALL_USERS, USERS_BY_LASTFM
    users = {}
    for u in CONF['users']:
        if u['lastfm'] in USERS_BY_LASTFM:
            user = USERS_BY_LASTFM[u['lastfm']]
            user.buffers = u['buffers']
        else:
            user = User(u['lastfm'], u['buffers'])
        users[user.lastfm_name] = user
    ALL_USERS = list(users.values())
    USERS_BY_LASTFM = users
ON_CONF_CHANGED.append(initialize_users)

def do_follow(bufname, user):
    for u in CONF['users']:
        if u['lastfm'] == user:
            if bufname in u['buffers']:
                return False
            u['buffers'].append(bufname)
            return True
    CONF['users'].append({
        'lastfm': user,
        'buffers': [bufname],
        })
    return True

def do_unfollow(bufname, user):
    do_remove = None
    for u in CONF['users']:
        if u['lastfm'] == user:
            if bufname not in u['buffers']:
                return False
            u['buffers'].remove(bufname)
            if len(u['buffers']) == 0:
                do_remove = u
                break
            return True
    if do_remove is not None:
        CONF['users'].remove(do_remove)
        return True
    return False

def get_following(bufname):
    users = []
    for u in CONF['users']:
        if bufname in u['buffers']:
            users.append(u)
    return users

def run_command(net, chan, args):
    bufname = '{},{}'.format(net, chan)
    buf = weechat.info_get('irc_buffer', bufname)
    if len(args) < 1:
        return
    if args[0] == 'follow':
        if do_follow(bufname, args[1]):
            conf_changed()
            save_conf()
            weechat.command(buf, u'/say \0032now following {}'.format(args[1]))
        else:
            weechat.command(buf, u'/say \0032already following {}'.format(args[1]))
        return
    if args[0] == 'unfollow':
        if do_unfollow(bufname, args[1]):
            conf_changed()
            save_conf()
            weechat.command(buf, u'/say \0032unfollowed {}'.format(args[1]))
        else:
            weechat.command(buf, u'/say \0032not following {}'.format(args[1]))
        return
    if args[0] == 'following':
        users = get_following(bufname)
        if len(users) == 0:
            weechat.command(buf, u'/say \0032not following anybody!')
        else:
            weechat.command(buf, u'/say \0032following: {}'.format(', '.join(
                u['lastfm'] for u in users)))
        return
    if args[0] == 'log':
        if log_set_level(args[1]):
            weechat.command(buf, u'/say \00302logging at {}'.format(LOGLEVELS[LOGLEVEL]))
        else:
            weechat.command(buf, u'/say \00302{} is not a valid log level'.format(args[1]))

def try_command(data, signal, signal_data):
    sig = weechat.info_get_hashtable('irc_message_parse', {
        'message': signal_data})
    server = signal.split(',')[0]
    args = sig['arguments'].split(' :', 1)
    tail = ''
    if len(args) > 1:
        tail = args[1]
    args = args[0].split()
    nick = weechat.info_get('irc_nick', server)
    tail = tail.lstrip()
    if not tail.startswith(nick):
        return weechat.WEECHAT_RC_OK
    data = tail.split()
    if len(data) < 2:
        return weechat.WEECHAT_RC_OK
    run_command(server, sig['channel'], data[1:])
    return weechat.WEECHAT_RC_OK

weechat.register('nya', 'aji', '1.0', 'MIT', 'nya!', '', '')

for option, dfl in OPTIONS.items():
    if not weechat.config_is_set_plugin(option):
        weechat.config_set_plugin(option, dfl)

load_conf()
weechat.hook_signal('*,irc_in_privmsg', 'try_command', '')
on_timer_fire('', '') #HAX ROFL
alert(u'(nya): nya (re)loaded')
