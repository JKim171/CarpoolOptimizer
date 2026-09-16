#!/bin/bash
# First-boot provisioning. This runs ONCE, at initial launch, and never again —
# editing it later does not re-run it and does not replace the instance. Ongoing
# provisioning is the deploy path's job (SSM Run Command, design §10.1), not this
# script's. Keep it to what must exist before the first deploy can work.
set -euxo pipefail

# Swap. The box has 2 GB of RAM against a sizing estimate of ~1-1.1 GB
# (design §10.1), so the margin is thin. Swap turns a transient spike into
# slowness rather than the OOM killer choosing a victim — and the victim it
# would choose is usually Postgres, the one process holding the only copy of
# anything.
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=${swap_size_mb}
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# Swap is an emergency margin, not a place to page Postgres' working set out to
# under normal load.
echo 'vm.swappiness=10' > /etc/sysctl.d/99-swappiness.conf
sysctl -p /etc/sysctl.d/99-swappiness.conf

dnf update -y
dnf install -y docker
systemctl enable --now docker
usermod -aG docker ec2-user

# Compose v2+ ships as a CLI plugin and AL2023 has no package for it, so it is
# fetched directly and pinned. aarch64: this is Graviton.
install -d /usr/libexec/docker/cli-plugins
curl -fsSL -o /usr/libexec/docker/cli-plugins/docker-compose \
  "https://github.com/docker/compose/releases/download/${compose_version}/docker-compose-linux-aarch64"
chmod +x /usr/libexec/docker/cli-plugins/docker-compose
docker compose version

# The SSM agent is preinstalled and enabled on AL2023, so nothing here starts it.
# If a session will not open, the cause is the instance role or egress, not this.
