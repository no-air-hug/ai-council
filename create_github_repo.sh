#!/bin/bash
# Create GitHub Repository Script
# Usage: ./create_github_repo.sh [repository-name] [public|private]

REPO_NAME="${1:-ai-council}"
VISIBILITY="${2:-public}"

echo "=========================================="
echo "Creating GitHub Repository: $REPO_NAME"
echo "Visibility: $VISIBILITY"
echo "=========================================="
echo ""

# Check if GitHub token is set
if [ -z "$GITHUB_TOKEN" ]; then
    echo "ERROR: GITHUB_TOKEN environment variable is not set."
    echo ""
    echo "To create a Personal Access Token:"
    echo "1. Go to: https://github.com/settings/tokens"
    echo "2. Click 'Generate new token' -> 'Generate new token (classic)'"
    echo "3. Name it 'AI Council Repo Creation'"
    echo "4. Select scope: 'repo' (full control of private repositories)"
    echo "5. Click 'Generate token' and copy it"
    echo ""
    echo "Then run:"
    echo "  export GITHUB_TOKEN=your_token_here"
    echo "  ./create_github_repo.sh"
    echo ""
    exit 1
fi

# Create repository via GitHub API
echo "Creating repository on GitHub..."
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    https://api.github.com/user/repos \
    -d "{\"name\":\"$REPO_NAME\",\"description\":\"Local multi-agent LLM debate system with persona-driven workers\",\"private\":$([ \"$VISIBILITY\" = \"private\" ] && echo \"true\" || echo \"false\"),\"auto_init\":false}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "201" ]; then
    echo "✓ Repository created successfully!"
    echo ""
    
    # Extract clone URL
    CLONE_URL=$(echo "$BODY" | grep -o '"clone_url":"[^"]*"' | cut -d'"' -f4)
    SSH_URL=$(echo "$BODY" | grep -o '"ssh_url":"[^"]*"' | cut -d'"' -f4)
    
    echo "Repository URLs:"
    echo "  HTTPS: $CLONE_URL"
    echo "  SSH:   $SSH_URL"
    echo ""
    
    # Add remote and push
    echo "Adding remote 'origin'..."
    git remote add origin "$CLONE_URL" 2>/dev/null || git remote set-url origin "$CLONE_URL"
    
    echo "Pushing to GitHub..."
    git push -u origin main
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "=========================================="
        echo "✓ Success! Repository is now on GitHub:"
        echo "  https://github.com/$(echo "$BODY" | grep -o '"full_name":"[^"]*"' | cut -d'"' -f4)"
        echo "=========================================="
    else
        echo ""
        echo "⚠ Repository created but push failed."
        echo "You can push manually with:"
        echo "  git push -u origin main"
    fi
elif [ "$HTTP_CODE" = "422" ]; then
    echo "⚠ Repository '$REPO_NAME' might already exist."
    echo "Trying to add it as remote and push..."
    git remote add origin "https://github.com/$GITHUB_USERNAME/$REPO_NAME.git" 2>/dev/null || \
    git remote set-url origin "https://github.com/$GITHUB_USERNAME/$REPO_NAME.git"
    git push -u origin main
else
    echo "✗ Failed to create repository."
    echo "HTTP Code: $HTTP_CODE"
    echo "Response: $BODY"
    exit 1
fi

