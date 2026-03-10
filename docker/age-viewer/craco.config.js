/**
 * CRACO webpack override for Apache AGE Viewer.
 *
 * Problem: CRA's second babel-loader rule processes node_modules (to ensure
 * ES-module compatibility). weaverjs/dist/weaver.js is a large minified bundle
 * whose AST depth overflows @babel/traverse's call stack.
 *
 * Fix: exclude weaverjs from EVERY babel-loader rule so it is handled only by
 * webpack's own (non-recursive) parser.
 */
module.exports = {
  webpack: {
    configure: (webpackConfig) => {
      const oneOfRule = webpackConfig.module.rules.find(
        (rule) => Array.isArray(rule.oneOf),
      );

      if (oneOfRule) {
        oneOfRule.oneOf.forEach((rule) => {
          const isBabelLoader =
            (rule.loader && String(rule.loader).includes('babel-loader')) ||
            (Array.isArray(rule.use) &&
              rule.use.some(
                (u) => u.loader && String(u.loader).includes('babel-loader'),
              ));

          if (isBabelLoader) {
            if (!rule.exclude) {
              rule.exclude = /weaverjs/;
            } else if (Array.isArray(rule.exclude)) {
              rule.exclude.push(/weaverjs/);
            } else {
              rule.exclude = [rule.exclude, /weaverjs/];
            }
          }
        });
      }

      return webpackConfig;
    },
  },
};
