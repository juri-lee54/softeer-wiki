#!/bin/bash
# docker 설치 및 실행을 자동화 하는 자동화 스크립트

#!/bin/bash
exec > /var/log/user-data.log 2>&1
set -x

# apt가 IPv4만 사용하도록 강제 (IPv6 라우팅 문제 회피)
echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4

apt-get update -y
apt-get install -y docker.io
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

echo "Docker installation complete" >> /var/log/user-data.log