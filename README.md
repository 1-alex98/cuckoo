# Cuckoo Sandbox Fork

This fork is for analysing files with Cuckoo primarily on Ubuntu18.04 guests with Virtualbox5.2.

## Setup for analyzing
```shell
  apt install python2 -y
  virtualenv cuckoo-venv -p python2.7
  source cuckoo-venv/bin/activate
  curl https://bootstrap.pypa.io/get-pip.py --output get-pip.py
  python2 get-pip.py
  wget http://archive.ubuntu.com/ubuntu/pool/main/libv/libvpx/libvpx5_1.7.0-3_amd64.deb
  dpkg -i libvpx5_1.7.0-3_amd64.deb
  wget https://download.virtualbox.org/virtualbox/5.2.40/virtualbox-5.2_5.2.40-137108~Ubuntu~bionic_amd64.deb
  apt install ./virtualbox-5.2_5.2.40-137108~Ubuntu~bionic_amd64.deb -y
  adduser cuckoo
  sudo usermod -a -G vboxusers cuckoo
  groupadd pcap
  sudo usermod -a -G pcap cuckoo
  sudo chgrp pcap /usr/sbin/tcpdump
  sudo setcap cap_net_raw,cap_net_admin=eip /usr/sbin/tcpdump
  git clone https://github.com/axel1200/cuckoo
  pip install cuckoo
  mv new_config_files/reporting.conf $CWD/conf/reporting.conf
  VBoxManage hostonlyif create
  VBoxManage hostonlyif ipconfig vboxnet0 --ip 192.168.56.1 --netmask 255.255.255.0
  cuckoo -d
```
