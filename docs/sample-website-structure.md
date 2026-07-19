# Sample Git Repository Structure for Gym Website

Here's how your Git repository should be structured:

```
gym-website/                    # Repository root
├── index.html                  # Main HTML file (your current gym guide)
├── assets/                     # Static assets
│   ├── css/
│   │   └── style.css          # Your CSS styles
│   ├── js/
│   │   └── script.js          # Any JavaScript (optional)
│   └── images/
│       ├── logo.png
│       └── favicon.ico
├── README.md                   # Repository documentation
└── .gitignore                  # Git ignore file
```

## Creating the Repository

### Option 1: Start with current website content

```bash
# Create local directory
mkdir gym-website
cd gym-website

# Copy current website from server
scp root@192.168.1.11:/var/www/html/index.html .

# Initialize Git
git init
git add index.html
git commit -m "Initial commit: gym workout guide"

# Add remote and push
git remote add origin https://github.com/YOUR_USERNAME/gym-website.git
git branch -M main
git push -u origin main
```

### Option 2: Create new repository on GitHub first

1. Go to GitHub.com
2. Create new repository named "gym-website"
3. Clone it locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/gym-website.git
   cd gym-website
   ```
4. Copy your website files into the repository
5. Commit and push:
   ```bash
   git add .
   git commit -m "Add gym website files"
   git push origin main
   ```

## Sample .gitignore

```
# OS generated files
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
ehthumbs.db
Thumbs.db

# Backup files
*.backup
*.bak
*.tmp

# Editor files
*.swp
*.swo
*~

# Logs
*.log
```

## Deployment Workflow

Once your repository is set up:

1. **Make changes** to your website files locally or directly on GitHub
2. **Commit and push** changes to the repository
3. **Run deployment**:
   ```bash
   ./scripts/deploy.sh deploy https://github.com/YOUR_USERNAME/gym-website.git
   ```

The Ansible script will:
- Pull the latest changes from your repository
- Deploy them to your server
- Keep a backup of the previous version
- Restart Apache if needed

## Example: Updating the Workout Guide

```bash
# Clone your repository (if not already done)
git clone https://github.com/YOUR_USERNAME/gym-website.git
cd gym-website

# Edit the index.html file
vim index.html  # or use your preferred editor

# Commit changes
git add index.html
git commit -m "Update workout schedule for July 2026"
git push origin main

# Deploy to server
cd ../gym-website-ansible
./scripts/deploy.sh quick  # Quick deployment without backup
```

This workflow allows you to:
- Track all changes to your website in version control
- Have a backup of every version
- Deploy updates with a single command
- Roll back to previous versions if needed