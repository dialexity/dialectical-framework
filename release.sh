#!/bin/bash

# Script to bump version and publish to PyPI
# Usage: ./release.sh [patch|minor|major]
#   - Defaults to patch if no argument provided
#   - Shows what would happen and prompts for confirmation

VERSION_TYPE=${1:-patch}

if [[ ! "$VERSION_TYPE" =~ ^(patch|minor|major)$ ]]; then
    echo "❌ Invalid version type. Use: patch, minor, or major"
    exit 1
fi

# Check current branch
CURRENT_BRANCH=$(git branch --show-current)
if [[ "$CURRENT_BRANCH" != "main" ]]; then
    echo "❌ Releases must be made from the main branch. Currently on: $CURRENT_BRANCH"
    exit 1
fi

# Check git status (including untracked files)
if ! git diff --quiet || ! git diff --cached --quiet || [[ -n $(git ls-files --others --exclude-standard) ]]; then
    echo "❌ Repository has uncommitted or untracked changes. Please commit or stash changes before releasing."
    echo ""
    echo "Repository status:"
    git status --porcelain
    exit 1
fi

CURRENT_VERSION=$(poetry version -s)

# Calculate what the new version would be by temporarily bumping
poetry version "$VERSION_TYPE" > /dev/null
NEW_VERSION=$(poetry version -s)
# Reset back to original version
poetry version "$CURRENT_VERSION" > /dev/null

echo "🔍 RELEASE PREVIEW"
echo "Current version: $CURRENT_VERSION"
echo "New version would be: $NEW_VERSION ($VERSION_TYPE bump)"
echo ""
echo "This will:"
echo "  1. Bump version from $CURRENT_VERSION to $NEW_VERSION"
echo "  2. Commit the version bump"
echo "  3. Create git tag v$NEW_VERSION"
echo "  4. Push commit and tag to remote"
echo "  5. Build the package"
echo "  6. Publish to PyPI"
echo ""

read -p "Do you want to proceed? [y/N]: " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "🚀 EXECUTING RELEASE"
    echo "Bumping $VERSION_TYPE version..."
    poetry version "$VERSION_TYPE"
    echo ""
    echo "Committing version bump..."
    git add pyproject.toml
    git commit -m "Bump version to $NEW_VERSION"
    echo ""
    echo "Creating tag v$NEW_VERSION..."
    git tag "v$NEW_VERSION"
    echo ""
    echo "Pushing commit to remote..."
    git push
    echo ""
    echo "Pushing tag to remote..."
    git push origin "v$NEW_VERSION"
    echo ""
    echo "Building and publishing to PyPI..."
    poetry publish --build
    echo ""
    echo "Release complete! Package $NEW_VERSION published to PyPI 🚀"
else
    echo ""
    echo "Release cancelled."
fi