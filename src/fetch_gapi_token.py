import pytube

import pytube_patch


pytube_patch.init()


if __name__ == '__main__':
    try:
        pytube.YouTube('https://www.youtube.com/watch?v=YE7VzlLtp-4', use_oauth=True, allow_oauth_cache=True).streams
    except Exception:
        pass
