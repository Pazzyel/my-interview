# riton-agent

## 注意

RocketMQ 需要安装的依赖

```bash
pip install rocketmq-python-client
```

rocketmq-python-client 是 RocketMQ 5.x 版本的客户端，纯python实现。但无法再通过旧的方法进行连接

原来的方法是填写name server的地址（默认9876端口），客户端从name server获取对应topic所在broker的地址，再通过broker地址发消息到broker

5.x之后，客户端只和proxy通信，由proxy自己负责向name server请求地址，和broker通信。因此要填写proxy的地址（如果是local部署，默认是8081的gRPC端口）

如果有需要装dashboard的，它的默认端口8080已经被proxy用了（proxy使用8080，8081两个端口），因此它的默认端口改成了8082。只不过它的文档没有更新，还是8080

旧的 4.x 版本客户端 `rocketmq-client-python` 已经不再维护