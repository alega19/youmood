import pathlib
import re

import pytube.cipher
import pytube.exceptions
import pytube.innertube


def init():
    pytube.innertube._cache_dir = pathlib.Path(__file__).parent.resolve() / "pytube_cache"
    pytube.innertube._cache_dir.mkdir(parents=True, exist_ok=True)
    pytube.innertube._token_file = pytube.innertube._cache_dir / pathlib.Path(pytube.innertube._token_file).name
    pytube.cipher.get_throttling_function_name = _get_throttling_function_name


def _get_throttling_function_name(js):
    function_patterns = [
        r'a\.[a-zA-Z]\s*&&\s*\([a-z]\s*=\s*a\.get\("n"\)\)\s*&&.*?\|\|\s*([a-z]+)',
        r'\([a-z]\s*=\s*([a-zA-Z0-9$]+)(\[\d+\])?\([a-z]\)',
    ]
    for pattern in function_patterns:
        regex = re.compile(pattern)
        function_match = regex.search(js)
        if function_match:
            if len(function_match.groups()) == 1:
                return function_match.group(1)
            idx = function_match.group(2)
            if idx:
                idx = idx.strip("[]")
                array = re.search(
                    r'var {nfunc}\s*=\s*(\[.+?\]);'.format(
                        nfunc=re.escape(function_match.group(1))),
                    js
                )
                if array:
                    array = array.group(1).strip("[]").split(",")
                    array = [x.strip() for x in array]
                    return array[int(idx)]

    raise pytube.exceptions.RegexMatchError(
        caller="get_throttling_function_name", pattern="multiple"
    )
