import json
import urllib
import time
import traceback

USERS = [
    'theta4',
    'CorgiDude',
    'therealelizacat',
    'alyxw',
    'foxiepaws',
    ]

BUFFER = 'interlinked,#music'

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
        weechat.prnt(MUSIC, '  !! {}'.format(str(e)))
        for ln in traceback.format_exc().split('\n'):
            weechat.prnt(MUSIC, ln)
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
        self.image        = detext(kw.get('image',       None))
        self.url          = detext(kw.get('url',         None))
        self.streamable   = detext(kw.get('streamable',  None))
        self.date         = detext(kw.get('date',        None))
        self.artist       = detext(kw.get('artist',      None))
        self.mbid         = detext(kw.get('mbid',        None))
        self.album        = detext(kw.get('album',       None))
        self.name         = detext(kw.get('name',        None))

        self.attrs        = kw.get('@attr', {})

    def __repr__(self):
        return 'Track({} by {})'.format(self.name, self.artist)

class User(object):
    def __init__(self, lastfm_name):
        self.lastfm_name  = lastfm_name

        self.last_track   = None
        self.last_poll    = None

    def __repr__(self):
        return 'User({})'.format(self.lastfm_name)


def get_tracks(u, on_complete):
    def x(d):
        if 'recenttracks' not in d or 'track' not in d['recenttracks']:
            on_complete(False, d, u)
        tracks = []
        for t in d['recenttracks']['track']:
            tracks.append(Track(**t))
        on_complete(True, tracks, u)
    if not LASTFM_API_KEY():
        on_complete(False, {u'error': '-1', u'message': 'no lastfm key'}, u)
        return
    get_json(lastfm_url('user.getRecentTracks', user=u.lastfm_name, limit='10'), x)

def get_video(track, on_complete):
    def x(d):
        if 'kind' not in d or d['kind'] != 'youtube#searchListResponse':
            on_complete(None)
        first = d['items'][0]
        if 'kind' not in first or first['kind'] != 'youtube#searchResult':
            on_complete(None)
        vid = first['id']
        if 'kind' not in vid or vid['kind'] != 'youtube#video':
            on_complete(None)
        on_complete(vid['videoId'])
    if not YOUTUBE_API_KEY():
        on_complete(None)
        return
    get_json(youtube_url('search', part='snippet',
                q='{} {}'.format(track.artist, track.name),
                maxResults=1,
                type='video'), x)

def do_poll(u, on_complete):
    def request_completed(ok, tracks, u):
        if not ok:
            weechat.prnt(MUSIC, '  !! #{}: {}'.format(
                    tracks[u'error'], tracks[u'message']))
            return
        i = -1
        for j, t in enumerate(tracks):
            if u'nowplaying' in t.attrs and t.attrs['nowplaying'] == u'true':
                i = j
                break
        if i == -1:
            return
        if u.last_track is not None:
            if u.last_track.name == tracks[i].name:
                return
        weechat.prnt(MUSIC, '{}: {}'.format(repr(u), repr(tracks[i])))
        u.last_track = tracks[i]
        x = u.last_poll
        u.last_poll = time.time()
        if x is None:
            return
        on_complete(u)
    get_tracks(u, request_completed)

def on_one_fire(data, remaining):
    global MUSIC
    MUSIC = weechat.info_get('irc_buffer', BUFFER)
    def on_complete(u):
        def got_video_id(vid):
            weechat.command(MUSIC, '/say \0033 {} now listening to "{}" by {}{}'
                .format(u.lastfm_name, u.last_track.name, u.last_track.artist,
                '' if vid is None else ': http://youtu.be/{}'.format(vid))
                )
        get_video(u.last_track, got_video_id)
    u = ALL_USERS[int(remaining)]
    do_poll(u, on_complete)
    return weechat.WEECHAT_RC_OK

def on_timer_fire(data, remaining):
    global MUSIC
    MUSIC = weechat.info_get('irc_buffer', BUFFER)
    if not LASTFM_API_KEY():
        weechat.prnt(MUSIC, '!!!! no lastfm key set')
        return weechat.WEECHAT_RC_ERROR
    if not YOUTUBE_API_KEY():
        weechat.prnt(MUSIC, 'warning: no youtube key')
    weechat.hook_timer(900, 0, len(ALL_USERS), 'on_one_fire', '')
    weechat.hook_timer((max(len(ALL_USERS), 5) + 2) * 1000,
                       0, 1, 'on_timer_fire', '')
    return weechat.WEECHAT_RC_OK

weechat.register('nya', 'aji', '1.0', 'MIT', 'nya!', '', '')

ALL_USERS = [User(u) for u in USERS]

for option, dfl in OPTIONS.items():
    if not weechat.config_is_set_plugin(option):
        weechat.config_set_plugin(option, dfl)

on_timer_fire('', '') #HAX ROFL
weechat.command(MUSIC, '/say \0032nya (re)loaded')
