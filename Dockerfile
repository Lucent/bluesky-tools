# Three stages: (1) Node builds flexforest's flextree.js bundle from its npm dependency --
# a gitignored build artifact, regenerated here, never committed; (2) python parses the
# archive and assembles the static /site; (3) the runtime image carries only /site + python.
FROM node:20-slim AS flextree
WORKDIR /ff
COPY flexforest/package.json ./
RUN npm install && npm run build

FROM python:3.12-slim AS build
ARG ARCHIVE_DID
WORKDIR /src
COPY thread_browser.py thread_graph.py browse.html layout.js layout-lab.html ./
COPY flexforest/flexforest.js flexforest/flexforest-view.js flexforest/flexforest.css ./flexforest/
COPY --from=flextree /ff/flextree.js ./flexforest/flextree.js
COPY ${ARCHIVE_DID}/ ./${ARCHIVE_DID}/
RUN mkdir -p /site/flexforest && \
    SUFFIX="${ARCHIVE_DID#did:plc:}" && \
    python thread_browser.py ${ARCHIVE_DID} --out "/site/${SUFFIX}.json" && \
    sed "s|__ARCHIVE_FILE__|${SUFFIX}.json|" browse.html > /site/index.html && \
    cp layout.js layout-lab.html /site/ && \
    cp flexforest/flexforest.js flexforest/flexforest-view.js flexforest/flexforest.css flexforest/flextree.js /site/flexforest/

FROM python:3.12-slim
COPY --from=build /site /site
COPY serve.py /serve.py
WORKDIR /site
USER nobody
EXPOSE 8000
# Static server with a content ETag + 304s (see serve.py) so a redeploy never serves a
# stale module from cache; Cloudflare is set to respect these origin headers.
CMD ["python", "/serve.py"]
