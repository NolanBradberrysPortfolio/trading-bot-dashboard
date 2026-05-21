$ErrorActionPreference = "Stop"

git checkout main
git subtree split --prefix public -b gh-pages-publish
git push origin gh-pages-publish:gh-pages --force
git branch -D gh-pages-publish
