# Static file server for the thread browser. Same as `python -m http.server` plus two
# things (Cloudflare is set to respect these origin headers):
#
#   - a proper content ETag: each served representation gets a hash of its bytes, and an
#     `If-None-Match` that matches is answered with 304 (no body). So after a redeploy only
#     files whose content actually changed re-transfer, and Cloudflare revalidates instead
#     of serving a stale module -- which is what was pairing a fresh index.html with an old
#     layout.js.
#
#   - build-time brotli: the Dockerfile writes a <file>.br beside every text asset; a
#     request whose Accept-Encoding lists br is answered from that sibling with
#     Content-Encoding: br and the original's Content-Type. No runtime compression --
#     the artifact is compressed once, at build, at quality 11. Each variant carries its
#     own ETag; Vary: Accept-Encoding keeps caches honest about the split.
#
# Cache-Control: max-age=0, must-revalidate forces revalidation on every request without
# disabling caching -- the 304 path still applies. (It's the no-cache behaviour without the
# no-cache token; change the one constant below if you want a real max-age later.)
import functools, hashlib, os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

CACHE_CONTROL = "max-age=0, must-revalidate"


class Handler(SimpleHTTPRequestHandler):
    _etags = {}   # path -> ((mtime_ns, size), etag); recomputed only when the file changes

    def _etag(self, path):
        try:
            st = os.stat(path)
        except OSError:
            return None
        key = (st.st_mtime_ns, st.st_size)
        hit = self._etags.get(path)
        if hit and hit[0] == key:
            return hit[1]
        h = hashlib.blake2b(digest_size=16)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        tag = '"%s"' % h.hexdigest()
        self._etags[path] = (key, tag)
        return tag

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            path = os.path.join(path, "index.html")   # a dir request ("/") is served as its index.html
        accepted = {t.split(";")[0].strip() for t in self.headers.get("Accept-Encoding", "").split(",")}
        self._enc = "br" if "br" in accepted and os.path.isfile(path + ".br") else None
        if self._enc:
            path += ".br"
        self._tag = self._etag(path)
        if self._tag and self.headers.get("If-None-Match") == self._tag:
            self.send_response(304)
            self.end_headers()   # adds ETag + Cache-Control + Vary below
            return None
        if not self._enc:
            return super().send_head()
        # The .br sibling: its own bytes and length, the original's Content-Type (mimetypes
        # knows .br is an encoding suffix, but stripping it keeps the lookup unambiguous).
        f = open(path, "rb")
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(path[:-3]))
        self.send_header("Content-Length", str(os.fstat(f.fileno()).st_size))
        self.send_header("Content-Encoding", "br")
        self.end_headers()
        return f

    def end_headers(self):
        if getattr(self, "_tag", None):
            self.send_header("ETag", self._tag)
        self.send_header("Cache-Control", CACHE_CONTROL)
        self.send_header("Vary", "Accept-Encoding")
        super().end_headers()


ThreadingHTTPServer(("", 8000), functools.partial(Handler, directory="/site")).serve_forever()
