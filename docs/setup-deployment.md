# Gym Website Ansible Deployment Setup

## Project Status
- **Location**: `/Users/denair/gym-website-ansible/gym-website-ansible/`
- **Target Host**: 192.168.1.11
- **Current Status**: Host not accessible (connection refused)

## Complete Setup Instructions

### 1. Prerequisites

Ensure the target server is running and accessible:

```bash
# Test basic connectivity
ping 192.168.1.11

# Test SSH access
ssh root@192.168.1.11
```

### 2. Server Requirements

The target server (192.168.1.11) needs:
- Linux OS (preferably RHEL/Fedora/CentOS)
- Apache httpd installed and running
- SSH server running on port 22
- Root SSH access configured

### 3. Quick Deployment Commands

Once connectivity is established:

**Test Connection:**
```bash
cd /Users/denair/gym-website-ansible/gym-website-ansible
ansible gym-server -m ping
```

**Deploy Local Website:**
```bash
cd /Users/denair/gym-website-ansible/gym-website-ansible
ansible-playbook playbooks/deploy-local.yml
```

**Full Git Deployment:**
```bash
cd /Users/denair/gym-website-ansible/gym-website-ansible
ansible-playbook playbooks/deploy-website.yml
```

### 4. Management Scripts Available

**Comprehensive Management:**
```bash
cd /Users/denair/gym-website-ansible/gym-website-ansible
./scripts/manage.sh help
```

**Common Operations:**
- `./scripts/manage.sh deploy` - Full deployment with backup
- `./scripts/manage.sh local` - Deploy local website/index.html
- `./scripts/manage.sh status` - Check server status
- `./scripts/manage.sh test` - Test connectivity and website
- `./scripts/manage.sh backup` - Create backup
- `./scripts/manage.sh logs` - View Apache logs

### 5. Available Playbooks

1. **playbooks/deploy-local.yml** - Deploy local website/index.html file
2. **playbooks/deploy-website.yml** - Deploy from Git repository
3. **playbooks/backup.yml** - Create backup of current site
4. **playbooks/rollback.yml** - Restore from backup
5. **playbooks/tests/test-playbooks.yml** - Comprehensive test suite
6. **playbooks/deploy-quick.yml** - Quick deployment without backup

### 6. Configuration Files

**inventory.yml** - Main configuration:
```yaml
all:
  hosts:
    gym-server:
      ansible_host: 192.168.1.11
      ansible_user: root
  vars:
    git_repo_url: "https://github.com/your-username/gym-website.git"
    git_branch: "main"
    web_root: "/var/www/html"
    backup_dir: "/var/backups/website"
```

**ansible.cfg** - Ansible settings:
```ini
[defaults]
inventory = inventory.yml
remote_user = root
host_key_checking = False
timeout = 30

[ssh_connection]
ssh_args = -o ControlMaster=auto -o ControlPersist=60s -o StrictHostKeyChecking=no
pipelining = True
```

### 7. Website Content

The project includes a complete gym/fitness website in `website/index.html` with:
- Exercise guides and routines
- White theme design
- Mobile responsive layout
- Pure HTML/CSS implementation

### 8. Testing Framework

Run comprehensive tests:
```bash
cd /Users/denair/gym-website-ansible/gym-website-ansible
ansible-playbook playbooks/tests/test-playbooks.yml
```

Or use the test runner:
```bash
cd /Users/denair/gym-website-ansible/gym-website-ansible
./scripts/run-tests.sh
```

### 9. Troubleshooting

**Connection Issues:**
1. Verify target host is running: `ping 192.168.1.11`
2. Check SSH service: `nmap -p 22 192.168.1.11`
3. Test SSH directly: `ssh root@192.168.1.11`
4. Check firewall settings on target

**Deployment Issues:**
1. Verify Apache is installed: `ansible gym-server -m shell -a "which httpd"`
2. Check Apache status: `ansible gym-server -m shell -a "systemctl status httpd"`
3. Verify disk space: `ansible gym-server -m shell -a "df -h"`

### 10. Quick Start (When Host Available)

```bash
# Navigate to project
cd /Users/denair/gym-website-ansible/gym-website-ansible

# Test connectivity
ansible gym-server -m ping

# Deploy website (local file)
ansible-playbook playbooks/deploy-local.yml

# Check deployment
curl -I http://192.168.1.11/

# View website
open http://192.168.1.11/
```

## Skill Integration

Use the `/gym-deploy` skill for easy management:
- `/gym-deploy` - Default deployment
- `/gym-deploy status` - System status
- `/gym-deploy test` - Run tests
- `/gym-deploy backup` - Create backup

## Next Steps

1. **Ensure Target Host Availability**: Make sure 192.168.1.11 is accessible
2. **Test Connectivity**: Run `ansible gym-server -m ping`
3. **Deploy Website**: Use any of the available playbooks
4. **Verify Deployment**: Check http://192.168.1.11/
5. **Set Up Monitoring**: Use management scripts for ongoing operations