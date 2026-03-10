# Apache AGE Viewer — Node 16
# CRA's node_modules babel-loader causes @babel/traverse to stack-overflow on
# weaverjs's deeply-nested minified bundle. Fix via CRACO: exclude weaverjs
# from every babel-loader rule so webpack's own parser handles it instead.
FROM node:16-bullseye-slim

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth 1 https://github.com/apache/age-viewer.git .

# Root deps
RUN npm install

# Backend deps (+ missing @babel/runtime for babel-node)
WORKDIR /src/backend
RUN npm install && npm install @babel/runtime

# Frontend deps + CRACO
WORKDIR /src/frontend
RUN npm install --legacy-peer-deps
RUN npm install --save-dev @craco/craco@6

# Inject CRACO config
COPY craco.config.js ./craco.config.js

WORKDIR /src/backend
# age-viewer ships meta_data.sql for PG 11-15 but not PG 16.
# The query is pure AGE catalog SQL — identical for PG 16.
RUN cp -r sql/15 sql/16

WORKDIR /src/frontend

# Patch package.json: swap react-scripts → craco for start/build
RUN node -p " \
  JSON.stringify((() => { \
    const p = require('./package.json'); \
    p.scripts.start = 'craco start'; \
    p.scripts.build = 'craco build'; \
    return p; \
  })(), null, 2)" > /tmp/pkg.json && mv /tmp/pkg.json package.json

WORKDIR /src

# Disable CRA's ESLint webpack plugin — age-viewer imports cytoscape/src/util
# (an internal path) which triggers import/no-unresolved and fails the build.
ENV DISABLE_ESLINT_PLUGIN=true

EXPOSE 3000

CMD ["npm", "start"]
