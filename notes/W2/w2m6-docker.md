# 목차
- [목차](#목차)
- [관련 개념](#관련-개념)
  - [Docker](#docker)
    - [Dockerfile](#dockerfile)
    - [컨테이너 레지스트리(Registry)](#컨테이너-레지스트리registry)
    - [Docker Desktop](#docker-desktop)
- [2026.07.08 잡업 과정 정리](#20260708-잡업-과정-정리)
  - [목표](#목표)
  - [1. EC2 인스턴스 생성](#1-ec2-인스턴스-생성)
    - [user-data.sh (최초 버전)](#user-datash-최초-버전)
  - [2. User-data 관련 트러블슈팅 (IPv6 문제)](#2-user-data-관련-트러블슈팅-ipv6-문제)
    - [수정된 user-data.sh](#수정된-user-datash)
  - [3. 퍼블릭 접속 문제 (Elastic IP)](#3-퍼블릭-접속-문제-elastic-ip)
  - [4. IAM 권한 문제 (교육용 계정 제약)](#4-iam-권한-문제-교육용-계정-제약)
    - [시도 1: IAM 역할 생성 → 실패](#시도-1-iam-역할-생성--실패)
    - [시도 2: Access Key 직접 생성 → 실패](#시도-2-access-key-직접-생성--실패)
    - [시도 3: MFA 기반 임시 자격증명 사용 (일단 인증 자체는 성공)](#시도-3-mfa-기반-임시-자격증명-사용-일단-인증-자체는-성공)
    - [최종 해결: EC2에 ECR 접근 권한이 있는 IAM 역할 부여](#최종-해결-ec2에-ecr-접근-권한이-있는-iam-역할-부여)
  - [5. 로컬에서 Docker 이미지 → ECR push (성공)](#5-로컬에서-docker-이미지--ecr-push-성공)
    - [리포지토리 생성](#리포지토리-생성)
    - [ECR 로그인](#ecr-로그인)
    - [로컬 이미지 확인](#로컬-이미지-확인)
    - [태그 달기](#태그-달기)
    - [push](#push)
  - [6. EC2에서 ECR pull 시도 → SCP(조직 정책) 장벽 → IAM 역할로 해결](#6-ec2에서-ecr-pull-시도--scp조직-정책-장벽--iam-역할로-해결)
  - [7. 이미지 아키텍처 불일치 문제 (Apple Silicon vs EC2)](#7-이미지-아키텍처-불일치-문제-apple-silicon-vs-ec2)
  - [8. EC2 디스크 용량 부족 문제](#8-ec2-디스크-용량-부족-문제)
  - [9. 컨테이너 실행](#9-컨테이너-실행)
  - [10. 데이터 파일 누락 문제](#10-데이터-파일-누락-문제)
  - [11. 커널 재시작(Kernel Restarting) 문제 — 조사 중](#11-커널-재시작kernel-restarting-문제--조사-중)

<br>

# 관련 개념
## Docker

: 컨테이너 기반 가상화 플랫폼, 응용 프로그램과 그 종속성을 격리된 환경인 컨테이너로 패키징하여 실행하는 기술

- **이미지** : 애플리케이션 + 실행 환경(OS, 라이브러리, 코드)을 하나로 패키징한 설계도 또는 스냅샷. 읽기 전용
- **컨테이너**: 이미지를 실제로 실행한 상태

### Dockerfile

: 이미지를 어떻게 만들지 정의하는 텍스트 파일

- FROM : 베이스 이미지
- COPY : 파일 복사
- RUN : 명령 실행 (이미지를 작성하기 위한 명령어)
- CMD : 컨테이너 실행 시 자동 실행할 명령

베이스 이미지 → 처음부터 OS를 세팅하지 않고, 이미 필요한 게 설치된 공식 이미지를 가져다 쓰는 것

과제에서 jupyter/scipy-notebook 같은 Jupyter 공식 이미지를 사용하면 Python + JupyterLab이 이미 세팅되어 있어 편함

### 컨테이너 레지스트리(Registry)

: 이미지를 저장하고 배포하는 저장소 (Docker Hub, AWS ECR)

- 로컬에서 만든 이미지를 EC2에서 바로 쓸 수 없으므로, 레지스트리에 push했다가 EC2에서 pull 하는 흐름이 필요함

### Docker Desktop

: 로컬 PC(맥/윈도우)에서 Docker를 사용할 수 있게 해주는 앱. 이걸로 이미지를 빌드하고, 로컬 테스트를 함

<br>

# 2026.07.08 잡업 과정 정리

## 목표
로컬에서 만든 Docker 이미지(JupyterLab + W1 노트북)를 AWS EC2에 배포해서, 브라우저로 접속하면 JupyterLab이 실행되도록 만들기.

<br>

## 1. EC2 인스턴스 생성

- **AMI**: Ubuntu Server 24.04 LTS
- **인스턴스 유형**: t2.micro (프리티어)
- **보안 그룹**: 22번(SSH), 8888번(JupyterLab) 포트 개방
- **User-data**: Docker 자동 설치 스크립트 등록

### user-data.sh (최초 버전)

```bash
#!/bin/bash
exec > /var/log/user-data.log 2>&1
set -x

apt-get update -y
apt-get install -y docker.io
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

echo "Docker installation complete" >> /var/log/user-data.log
```

<br>


## 2. User-data 관련 트러블슈팅 (IPv6 문제)

**문제**: `apt-get update`가 IPv6 네트워크 문제로 실패 → Docker 설치 자체가 안 됨

```
Cannot initiate the connection to security.ubuntu.com:80 (2606:4700:10::...)
Network is unreachable
```

**원인**: EC2에 IPv6 주소는 할당되어 있지만, 실제 IPv6 인터넷 라우팅이 제대로 안 잡혀있어서 패키지 서버 접속 실패.

**해결**: `Acquire::ForceIPv4` 설정을 추가해서 IPv4로 강제 접속하도록 수정.

### 수정된 user-data.sh

```bash
#!/bin/bash
exec > /var/log/user-data.log 2>&1
set -x

# IPv4 강제 설정 (IPv6 라우팅 문제 회피)
echo 'Acquire::ForceIPv4 "true";' > /etc/apt/apt.conf.d/99force-ipv4

apt-get update -y
apt-get install -y docker.io
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

echo "Docker installation complete" >> /var/log/user-data.log
```


<br>


## 3. 퍼블릭 접속 문제 (Elastic IP)

**문제**: EC2에 퍼블릭 IP가 자동 할당되지 않음

**해결**: Elastic IP(탄력적 IP)를 수동으로 할당하고 인스턴스에 연결

- EC2 콘솔 → 네트워크 및 보안 → 탄력적 IP → 할당(Allocate) → 인스턴스에 연결(Associate)
- 결과: 고정 퍼블릭 IP `<EC2_PUBLIC_IP>` 확보

<br>


## 4. IAM 권한 문제 (교육용 계정 제약)

### 시도 1: IAM 역할 생성 → 실패
```
User: .../<IAM_USERNAME> is not authorized to perform: iam:GetPolicyVersion
```

### 시도 2: Access Key 직접 생성 → 실패
```
is not authorized to perform: iam:CreateAccessKey
```

### 시도 3: MFA 기반 임시 자격증명 사용 (일단 인증 자체는 성공)

1. MFA 디바이스 등록 (Google Authenticator 등)
2. 임시 자격증명 발급 (기본 Access Key + MFA 코드 필요):

```bash
aws sts get-session-token \
    --serial-number arn:aws:iam::<AWS_ACCOUNT_ID>:mfa/<IAM_USERNAME> \
    --token-code 123456 \
    --duration-seconds 3600
```

3. 결과로 받은 값을 로컬 및 EC2 양쪽에 환경변수로 설정:

```bash
export AWS_ACCESS_KEY_ID=ASIAXXXXXXXXXXXXXXXX
export AWS_SECRET_ACCESS_KEY=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
export AWS_SESSION_TOKEN=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX...
```

4. 인증 확인:
```bash
aws sts get-caller-identity
```

```json
{
    "UserId": "<IAM_USER_ID>",
    "Account": "<AWS_ACCOUNT_ID>",
    "Arn": "arn:aws:iam::<AWS_ACCOUNT_ID>:user/edu/<IAM_USERNAME>"
}
```

→ 인증(`get-caller-identity`)까지는 성공했으나, 이후 EC2에서 `ecr:GetAuthorizationToken` 호출 시
SCP(조직 정책)에 의해 차단되는 문제가 별도로 발생 (아래 6번 항목 참고).

### 최종 해결: EC2에 ECR 접근 권한이 있는 IAM 역할 부여

관리자에게 요청해서 **EC2 인스턴스에 ECR 접근 권한이 포함된 IAM 역할**을 연결받음
(`AmazonEC2ContainerRegistryReadOnly` 정책 포함).

- EC2 콘솔 → 인스턴스 선택 → 작업(Actions) → 보안(Security) → **IAM 역할 수정(Modify IAM role)**
- 관리자가 만들어준 역할 선택 후 저장

이렇게 IAM 역할을 EC2에 직접 붙이니, Access Key/MFA 임시 토큰 없이도
EC2 자체적으로 ECR 인증이 자동으로 처리되어 **문제 해결됨**.


<br>


## 5. 로컬에서 Docker 이미지 → ECR push (성공)

- 로컬 이미지 이름: `w2m6`
- ECR 리포지토리 새로 생성: `juri-data-product`

### 리포지토리 생성
```bash
aws ecr create-repository --repository-name juri-data-product --region ap-northeast-2
```

### ECR 로그인
```bash
aws ecr get-login-password --region ap-northeast-2 | \
  docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com
```

### 로컬 이미지 확인
```bash
docker images
# REPOSITORY   TAG       IMAGE ID       ...
# w2m6         latest    6ed83d3d688a   ...
```

### 태그 달기
```bash
docker tag w2m6:latest <AWS_ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com/juri-data-product:latest
```

### push
```bash
docker push <AWS_ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com/juri-data-product:latest
```

**결과: push 성공**
```
latest: digest: sha256:6ed83d3d688ac6c0b031ead7ade6476cbca55a9de8342815b2b5b24be2f29af6 size: 856
```

<br>

## 6. EC2에서 ECR pull 시도 → SCP(조직 정책) 장벽 → IAM 역할로 해결

EC2에서 아래 명령어 실행 시:
```bash
aws ecr get-login-password --region ap-northeast-2 | \
  docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com
```

에러 발생 (Access Key, MFA 임시 토큰 등 어떤 인증 방식을 써도 동일하게 발생):
```
An error occurred (AccessDeniedException) when calling the GetAuthorizationToken operation:
User: arn:aws:iam::<AWS_ACCOUNT_ID>:user/edu/<IAM_USERNAME> is not authorized to perform:
ecr:GetAuthorizationToken on resource: * with an explicit deny in a service control policy:
arn:aws:organizations::<ORG_ACCOUNT_ID>:policy/<ORG_UNIT_ID>/service_control_policy/<SCP_POLICY_ID>
```

**원인**: 개별 IAM 사용자의 자격증명 방식 문제가 아니라, **EC2에서 나가는 요청 자체를 조직(Organization)
레벨의 SCP가 명시적으로 차단**하고 있었음. 로컬에서는 동일 계정으로 정상 작동했으나 EC2 안에서의
요청만 막혀 있어, 사용자/학생 단에서는 우회 불가능했던 문제.

**최종 해결**: 관리자에게 요청하여 **EC2 인스턴스에 ECR 접근 권한을 가진 IAM 역할을 직접 부여** →
Access Key나 임시 토큰 없이 EC2 자체 권한으로 인증되면서 `ecr:GetAuthorizationToken` 정상 통과.

```bash
aws ecr get-login-password --region ap-northeast-2 | \
  docker login --username AWS --password-stdin <AWS_ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com
# Login Succeeded
```

<br>

## 7. 이미지 아키텍처 불일치 문제 (Apple Silicon vs EC2)

`docker pull` 시도 시 에러:
```
Error response from daemon: no matching manifest for linux/amd64 in the manifest list entries:
no match for platform in manifest: not found
```

**원인**: 로컬 맥북이 Apple Silicon(arm64) 칩(`uname -m` → `arm64`)이라, `docker build`로
만든 이미지가 arm64용으로 빌드됨. EC2(t2.micro)는 x86_64(amd64) 아키텍처라 실행 불가.

**해결**: 빌드 시 플랫폼을 명시적으로 지정해서 amd64용 이미지로 다시 빌드 후 push.

```bash
docker build --platform linux/amd64 -t w2m6 .

docker tag w2m6:latest <AWS_ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com/juri-data-product:latest
docker push <AWS_ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com/juri-data-product:latest
```

<br>

## 8. EC2 디스크 용량 부족 문제

`docker pull` 진행 중 레이어 압축 해제 단계에서 에러:
```
failed to extract layer ... write /var/lib/containerd/.../libarrow.so...: no space left on device
```

**확인**:
```bash
df -h
# /dev/root  6.7G  2.8G  3.9G  43%  /   ← 여유 공간 부족
```
(`docker system prune -a -f`로도 회수된 공간 0B — 캐시 문제가 아니라 애초에 볼륨 자체가 작았던 것)

**해결**: EBS 볼륨 크기를 20GB로 늘리고, 파일시스템도 함께 확장.

```bash
# 1) AWS 콘솔 → EC2 → 볼륨(Volumes) → 볼륨 수정(Modify volume) → 20GiB로 변경

# 2) EC2 내부에서 파티션/파일시스템 확장
lsblk
sudo growpart /dev/xvda 1
sudo resize2fs /dev/xvda1

# 3) 확인
df -h
```

이후 `docker pull` 재시도 시 정상 완료:
```
Status: Downloaded newer image for <AWS_ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com/juri-data-product:latest
```

<br>

## 9. 컨테이너 실행

```bash
docker run -d -p 8888:8888 --restart unless-stopped \
  <AWS_ACCOUNT_ID>.dkr.ecr.ap-northeast-2.amazonaws.com/juri-data-product:latest

docker ps
```

브라우저 접속: `http://<EC2_PUBLIC_IP>:8888/lab`

<br>

## 10. 데이터 파일 누락 문제

W1 노트북 실행 시 데이터 파일이 이미지 안에 포함되지 않아 정상 실행이 안 되는 상황 발견.

**해결 방향**: Dockerfile에 데이터 파일도 함께 `COPY`하도록 추가한 뒤 재빌드/재push 필요.

```dockerfile
COPY data/ /home/jovyan/work/data/
```

빠른 확인용 임시 방법 (컨테이너 재시작 시 사라짐, 정식 해결 아님):
```bash
scp -i <KEY_PAIR>.pem data/sales.csv ubuntu@<EC2_PUBLIC_IP>:~/
docker cp ~/sales.csv <컨테이너ID>:/home/jovyan/work/data/sales.csv
```

<br>

## 11. 커널 재시작(Kernel Restarting) 문제 — 조사 중

노트북 셀 실행 중 `Kernel Restarting: The kernel for w2m5.ipynb appears to have died` 발생.

**추정 원인**: t2.micro의 메모리(1GB)가 부족해서 커널이 OOM(Out of Memory)으로 강제 종료됨.

**확인 방법**:
```bash
free -h
dmesg | grep -i "killed process"
```

**해결 방안 (예정)**:
```bash
# Swap 메모리 2GB 추가
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile swap swap defaults 0 0' | sudo tee -a /etc/fstab
```