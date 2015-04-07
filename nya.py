import json
import urllib
import time
import traceback

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

LASTFM_API_ROOT  = option('lastfm.root')
LASTFM_API_KEY   = option('lastfm.key')
YOUTUBE_API_ROOT = option('youtube.root')
YOUTUBE_API_KEY  = option('youtube.key')

def lastfm_url(method, **params):
    q = {
        'format': 'json',
        'api_key': LASTFM_API_KEY(),
        'method': method,
        }
    q.update(params)
    return LASTFM_API_ROOT() + '?' + urllib.urlencode(q)

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
        weechat.prnt('', '  !! {}'.format(str(e)))
        for ln in traceback.format_exc().split('\n'):
            weechat.prnt('', ln)
    del URL_REQUEST_TMP[cb]
    return weechat.WEECHAT_RC_OK
def get_data(url, cb):
    global URL_REQUEST_LAST
    URL_REQUEST_LAST += 1
    k = str(URL_REQUEST_LAST)
    URL_REQUEST_TMP[k] = {'cb':cb, 'data':''}
    weechat.hook_process('url:{}'.format(url), 5*1000, 'url_finished', k)

def get_json(url, on_complete):
    def x(d):
        on_complete(json.loads(d))
    get_data(url, x)

class Track(object):
    def __init__(self, **kw):
        self.image        = detext(kw.get(u'image',       None))
        self.url          = detext(kw.get(u'url',         None))
        self.streamable   = detext(kw.get(u'streamable',  None))
        self.date         = detext(kw.get(u'date',        None))
        self.artist       = detext(kw.get(u'artist',      None))
        self.mbid         = detext(kw.get(u'mbid',        None))
        self.album        = detext(kw.get(u'album',       None))
        self.name         = detext(kw.get(u'name',        None))

        self.attrs        = kw.get('@attr', {})

    def __repr__(self):
        return u'Track({} by {})'.format(self.name, self.artist)

class User(object):
    def __init__(self, lastfm_name, buffers):
        self.lastfm_name  = lastfm_name
        self.buffers      = buffers

        self.last_track   = None
        self.last_poll    = None

    def __repr__(self):
        return u'User({})'.format(self.lastfm_name)


def get_tracks(u, on_complete):
    def x(d):
        if u'recenttracks' not in d or u'track' not in d[u'recenttracks']:
            on_complete(False, d, u)
        tracks = []
        for t in d[u'recenttracks'][u'track']:
            tracks.append(Track(**t))
        on_complete(True, tracks, u)
    if not LASTFM_API_KEY():
        on_complete(False, {u'error': '-1', u'message': 'no lastfm key'}, u)
        return
    get_json(lastfm_url('user.getRecentTracks', user=u.lastfm_name, limit='10'), x)

def get_video(track, on_complete):
    def x(d):
        if u'kind' not in d or d[u'kind'] != u'youtube#searchListResponse':
            on_complete(None)
            return
        first = d[u'items'][0]
        if u'kind' not in first or first[u'kind'] != u'youtube#searchResult':
            on_complete(None)
            return
        vid = first[u'id']
        if u'kind' not in vid or vid[u'kind'] != u'youtube#video':
            on_complete(None)
            return
        on_complete(vid[u'videoId'])
    if not YOUTUBE_API_KEY():
        on_complete(None)
        return
    get_json(youtube_url(u'search', part=u'snippet',
                q=u'{} {}'.format(track.artist, track.name),
                maxResults=1,
                type=u'video'), x)

def do_poll(u, on_complete):
    def request_completed(ok, tracks, u):
        if not ok:
            weechat.prnt('', u'  !! {}: #{}: {}'.format(
                    repr(u), tracks[u'error'], tracks[u'message']))
            return
        i = -1
        for j, t in enumerate(tracks):
            if u'nowplaying' in t.attrs and t.attrs[u'nowplaying'] == u'true':
                i = j
                break
        if i == -1:
            return
        last_last_poll = u.last_poll
        u.last_poll = time.time()
        if last_last_poll is None:
            u.last_track = tracks[i]
            return
        if u.last_track is not None:
            if u.last_track.name == tracks[i].name:
                return
        weechat.prnt('', '{}: {}'.format(repr(u), repr(tracks[i])))
        u.last_track = tracks[i]
        on_complete(u)
    get_tracks(u, request_completed)

def on_one_fire(data, remaining):
    def on_complete(u):
        def got_video_id(vid):
            msg = (u'/say \0033 {} now listening to "{}" by {}{}'
                .format(u.lastfm_name, u.last_track.name, u.last_track.artist,
                u'' if vid is None else u': http://youtu.be/{}'.format(vid))
                )
            for b in u.buffers:
                buf = weechat.info_get('irc_buffer', b)
                if buf:
                    weechat.command(buf, msg)
        get_video(u.last_track, got_video_id)
    if int(remaining) < len(ALL_USERS):
        u = ALL_USERS[int(remaining)]
        do_poll(u, on_complete)
    return weechat.WEECHAT_RC_OK

def on_timer_fire(data, remaining):
    if not LASTFM_API_KEY():
        weechat.prnt('', '!!!! no lastfm key set')
        return weechat.WEECHAT_RC_ERROR
    if not YOUTUBE_API_KEY():
        weechat.prnt('', 'warning: no youtube key')
    if len(ALL_USERS) > 0:
        weechat.hook_timer(900, 0, len(ALL_USERS), 'on_one_fire', '')
    weechat.hook_timer((max(len(ALL_USERS), 5) + 2) * 1000,
                       0, 1, 'on_timer_fire', '')
    return weechat.WEECHAT_RC_OK

ALL_USERS = []
def initialize_users():
    global ALL_USERS
    ALL_USERS = [User(u['lastfm'], u['buffers']) for u in CONF['users']]
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
weechat.prnt('', u'(nya): nya (re)loaded')
