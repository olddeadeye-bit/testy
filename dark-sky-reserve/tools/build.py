#!/usr/bin/env python3
"""
Assemble dark-sky-reserve.html from src/.

The sources are split for the sake of reading them; the deliverable is a
single self-contained page. The sky plate is inlined as a data URI so the
file opens straight off the filesystem - no local server, no CDN, and
nothing that stops working when you are on a train.

Run:  python3 tools/build.py
"""

import base64
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, 'src')
OUT = os.path.join(ROOT, 'dark-sky-reserve.html')
OUT_ARTIFACT = os.path.join(ROOT, 'dark-sky-reserve.artifact.html')

SKY_JPG = os.path.join(ROOT, 'assets', 'sky.jpg')
SKY_LIGHT = os.path.join(ROOT, 'assets', 'sky_light.json')


def main():
    for f in (SKY_JPG, SKY_LIGHT):
        if not os.path.exists(f):
            sys.exit('missing %s - run tools/build_sky.py first' % f)

    shell = open(os.path.join(SRC, 'page.html')).read()
    css = open(os.path.join(SRC, 'style.css')).read()

    js_files = sorted(f for f in os.listdir(SRC) if f.endswith('.js'))
    parts = []
    for name in js_files:
        body = open(os.path.join(SRC, name)).read()
        parts.append('/* ---- %s %s */\n%s' % (name, '-' * max(0, 58 - len(name)), body))
    js = '\n\n'.join(parts)

    uri = 'data:image/jpeg;base64,' + base64.b64encode(open(SKY_JPG, 'rb').read()).decode()
    light = json.load(open(SKY_LIGHT))
    light.pop('_comment', None)

    js = js.replace('@@SKY_DATA_URI@@', uri)
    js = js.replace('@@SKY_LIGHT_JSON@@', json.dumps(light, separators=(',', ':')))

    for token, value in (('/*@CSS@*/', css), ('/*@JS@*/', js)):
        if token not in shell:
            sys.exit('page.html has lost its %s marker' % token)
        shell = shell.replace(token, value)

    left = re.findall(r'@@[A-Z_]+@@', shell)
    if left:
        sys.exit('unsubstituted tokens: %s' % sorted(set(left)))

    with open(OUT, 'w') as f:
        f.write(shell)
    print('wrote %s (%.0f KB, %d source files)'
          % (OUT, os.path.getsize(OUT) / 1024.0, len(js_files)))

    # A second flavour for hosting as an Artifact, which supplies its own
    # <!doctype>/<head>/<body> and wants only the content. Same bytes
    # otherwise - it is the standalone file with the document shell taken
    # off, so the two cannot drift apart.
    body = shell.split('<body>', 1)[1].rsplit('</body>', 1)[0]
    title = re.search(r'<title>(.*?)</title>', shell, re.S).group(1)
    art = ('<title>%s</title>\n<style>\n%s\n</style>\n%s'
           % (title, css, body))
    with open(OUT_ARTIFACT, 'w') as f:
        f.write(art)
    print('wrote %s (%.0f KB)' % (OUT_ARTIFACT, os.path.getsize(OUT_ARTIFACT) / 1024.0))


if __name__ == '__main__':
    main()
