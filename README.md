# riton-agent

## 注意

RocketMQ 需要安装的依赖

```bash
pip install rocketmq-python-client
```

rocketmq-python-client 底层依赖 RocketMQ 的 C++ 客户端库（librocketmq），仅支持 Linux 环境运行。在 Linux 上还需要安装 C++ 客户端：

```bash
# 以 CentOS/RHEL 为例
wget https://github.com/apache/rocketmq-client-cpp/releases/download/2.0.0/rocketmq-client-cpp-2.0.0-centos7.x86_64.rpm
sudo rpm -ivh rocketmq-client-cpp-2.0.0-centos7.x86_64.rpm
# 以 Ubuntu/Debian 为例
wget https://github.com/apache/rocketmq-client-cpp/releases/download/2.0.0/rocketmq-client-cpp-2.0.0.amd64.deb
sudo dpkg -i rocketmq-client-cpp-2.0.0.amd64.deb
```