# `nya` -- Nya's Your Amigo

Just kidding, forced backronyms are the worst. **nya** is a feature clone of a
bot called Enya that used to run in an IRC channel I'm in. The idea was that it
streamed LastFM "now playing" data for a set of users to the channel so that
people could check out what everybody else was listening to.

nya is both better and worse than Enya. It's better because it also searches
YouTube for the song and provides a link if it gets any results. It's worse
because it's basically not configurable at this point, and can only works for a
fixed number of users to a single buffer.

# Running `nya`

Please don't. Not yet.

But if you *insist*, then nya runs as a WeeChat plugin. The "configuration" is
at the top of the script, in the `USERS` and `BUFFER` variables. The LastFM and
YouTube API keys are WeeChat configuration options. Just run `/set *nya*` after
running the script and you'll figure out what you need to change. And because
I'm a jerk, I'm making you get your own API keys.

`/python reload nya` is your friend.
