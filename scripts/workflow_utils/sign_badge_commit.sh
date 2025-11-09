#!/usr/bin/env bash
set -euo pipefail

mkdir -p .github/public_keys
cat > gpg-batch <<'EOF'
Key-Type: RSA
Key-Length: 2048
Name-Real: Coverage Badge CI
Name-Email: actions@github.local
Expire-Date: 0
%no-protection
%commit
EOF

gpg --batch --gen-key gpg-batch
KEYID=$(gpg --list-keys --with-colons actions@github.local | awk -F: '/^pub/ {print $5; exit}')
echo "GPG Key ID: $KEYID"
gpg --armor --export actions@github.local > .github/public_keys/badge_signing.pub

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git config commit.gpgsign true
git config user.signingkey "$KEYID"

git add badges/coverage.svg badges/coverage.sig README.md .github/public_keys/badge_signing.pub reports/history/versions.json || true
git commit -S -m "ci: enable GPG commit signing and provenance trace for coverage badge" || echo "No changes to commit"

git push || echo "Push failed"
