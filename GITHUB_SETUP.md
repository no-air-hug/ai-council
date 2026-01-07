# GitHub Repository Setup Guide

This guide will help you create and push this project to GitHub.

## Prerequisites

- Git installed and configured
- GitHub account
- GitHub CLI (`gh`) installed (optional, but recommended)

## Step 1: Create Repository on GitHub

### Option A: Using Automated Script (Easiest with Git Bash)

**First, create a GitHub Personal Access Token:**

1. Go to: https://github.com/settings/tokens
2. Click "Generate new token" → "Generate new token (classic)"
3. Name it: "AI Council Repo Creation"
4. Select scope: **`repo`** (full control of private repositories)
5. Click "Generate token" and **copy the token** (you won't see it again!)

**Then run in Git Bash:**

```bash
# Set your token (replace YOUR_TOKEN with the actual token)
export GITHUB_TOKEN=YOUR_TOKEN

# Run the script (creates public repo by default)
./create_github_repo.sh

# Or specify name and visibility
./create_github_repo.sh ai-council public
./create_github_repo.sh ai-council private
```

The script will:
- Create the repository on GitHub
- Add it as remote 'origin'
- Push your code automatically

### Option B: Using GitHub CLI

```powershell
# Install GitHub CLI if not already installed
# Download from: https://cli.github.com/

# Authenticate (first time only)
gh auth login

# Create repository (public)
gh repo create ai-council --public --source=. --remote=origin --push

# Or create private repository
gh repo create ai-council --private --source=. --remote=origin --push
```

### Option C: Using GitHub Web Interface

1. Go to https://github.com/new
2. Repository name: `ai-council` (or your preferred name)
3. Description: "A local multi-agent LLM debate system where persona-driven workers generate diverse solutions"
4. Choose Public or Private
5. **DO NOT** initialize with README, .gitignore, or license (we already have these)
6. Click "Create repository"

## Step 2: Connect Local Repository to GitHub

If you used Option B (web interface), run these commands:

```powershell
# Navigate to project directory
cd "C:\Users\migue\OneDrive\Desktop\AI Council"

# Add remote (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/ai-council.git

# Or if using SSH:
git remote add origin git@github.com:YOUR_USERNAME/ai-council.git

# Verify remote
git remote -v
```

## Step 3: Commit and Push

```powershell
# Stage all files
git add .

# Create initial commit
git commit -m "Initial commit: AI Council multi-agent LLM system"

# Push to GitHub (first time)
git branch -M main
git push -u origin main
```

## Step 4: Verify

1. Visit your repository on GitHub: `https://github.com/YOUR_USERNAME/ai-council`
2. Verify all files are present
3. Check that `.gitignore` is working (venv/, __pycache__/, etc. should not be visible)

## Optional: Add Repository Topics

On GitHub, add topics to help others discover your project:
- `ai`
- `llm`
- `multi-agent`
- `ollama`
- `flask`
- `python`
- `local-ai`
- `debate-system`

## Optional: Add License

If you want to add a license:

```powershell
# Create LICENSE file (MIT example)
# Or download from: https://choosealicense.com/licenses/mit/

# Add and commit
git add LICENSE
git commit -m "Add MIT license"
git push
```

## Repository Settings Recommendations

1. **Description**: "Local multi-agent LLM debate system with persona-driven workers"
2. **Website**: Leave blank or add your project URL
3. **Topics**: Add relevant topics (see above)
4. **Features**:
   - ✅ Issues (enable for bug reports)
   - ✅ Discussions (optional, for community)
   - ✅ Wiki (optional)
   - ✅ Projects (optional)

## Next Steps

After pushing to GitHub:

1. **Add a README badge** (optional):
   ```markdown
   ![License](https://img.shields.io/badge/license-MIT-blue.svg)
   ```

2. **Create releases** for major versions:
   ```powershell
   git tag -a v0.1.0 -m "Initial release"
   git push origin v0.1.0
   ```

3. **Set up GitHub Actions** (optional) for CI/CD

4. **Add contributing guidelines** (CONTRIBUTING.md)

## Troubleshooting

### Authentication Issues

If you get authentication errors:

```powershell
# Use Personal Access Token instead of password
# Create token at: https://github.com/settings/tokens
# Use token as password when prompted

# Or configure credential helper
git config --global credential.helper wincred  # Windows
```

### Large Files

If you accidentally committed large files:

```powershell
# Remove from git history (use with caution!)
git filter-branch --tree-filter 'rm -f path/to/large/file' HEAD
git push origin --force --all
```

### Update Remote URL

If you need to change the remote URL:

```powershell
git remote set-url origin https://github.com/YOUR_USERNAME/ai-council.git
```

