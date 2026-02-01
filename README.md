# Mi-ChatBot - 小爱触屏音箱AI语音对话助手

## 项目简介

Mi-ChatBot 是一个基于小爱触屏音箱（LX04型号）上运行的大模型语音对话助手服务。该项目通过截获小爱音箱的ASR（自动语音识别）文本，调用大语言模型进行智能对话，并使用阿里云CosyVoice模型进行语音合成，实现完整的语音交互体验。

**⚠️ 重要提示：本项目仅适用于小爱触屏音箱LX04型号，其他型号未经测试，可能无法正常工作。**

## 功能特点

- 🎤 **语音识别**：截获小爱音箱的ASR识别结果
- 🤖 **智能对话**：支持接入各种大语言模型（如GPT、qwen等）
- 🔊 **语音合成**：使用阿里云CosyVoice-v2模型进行高质量语音合成
- 🛠️ **工具调用**：支持时间查询、数学计算、音量控制等功能
- 🔄 **流式响应**：支持流式文本生成和语音合成，提供更流畅的交互体验，支持说话打断

## 系统要求

- 小爱触屏音箱 **LX04型号**（已root） - **注意：本项目仅适用于LX04型号**
- Termux终端环境
- Python 3.10+
- 网络连接（用于调用API）

## 前置准备

### 1. Root小爱音箱
确保您的小爱触屏音箱（LX04型号）已经获得root权限。

### 2. 安装Termux及相关组件
在已root的小爱音箱上安装Termux终端环境：
- 下载并安装以下APK：
  - **Termux** - 主程序
  - **Termux:API** - 提供系统API访问（音量控制等功能必需）
  - **Termux:Boot** - 如需开机自启动服务（可选）
  
- 打开Termux，更新包管理器：
  ```bash
  pkg update && pkg upgrade
  ```

### 3. 在Termux中安装必要工具
```bash
# 安装Python
pkg install python

# 安装git
pkg install git

# 安装sox（音频播放器）
pkg install sox

# 安装termux-api（用于控制音量）
pkg install termux-api
```

## 安装步骤

1. **在Termux中克隆项目**
   ```bash
   git clone https://github.com/starstar222/Mi-ChatBot.git
   cd Mi-ChatBot
   ```

2. **安装Python依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **配置环境变量**
   
   复制环境变量示例文件并编辑：
   ```bash
   cp .env.example .env
   ```
   
   编辑 `.env` 文件，填入您的API密钥：
   ```env
   # 大语言模型配置
   BASE_URL=https://api.openai.com/v1  # 或其他兼容的API地址
   MODEL_NAME=gpt-4.1                  # 模型名称
   API_KEY=your_llm_api_key_here      # 您的LLM API密钥
   
   # 阿里云语音合成配置
   DASHSCOPE_API_KEY=your_dashscope_api_key_here  # 阿里云百炼API密钥
   ```

## API密钥获取

### 大语言模型API
- **OpenAI**: 访问 [OpenAI Platform](https://platform.openai.com/api-keys) 获取API密钥
- **其他模型**: 根据您选择的模型提供商获取相应的API密钥，国内用户推荐使用qwen

### 阿里云CosyVoice API
1. 访问 [阿里云百炼平台](https://dashscope.aliyun.com/)
2. 注册并登录账号
3. 在控制台创建API密钥
4. 确保账户有足够的额度或已开通相关服务

## 使用方法

### 基本使用

在Termux终端中运行主程序：
```bash
# 确保在项目目录下
cd ~/Mi-ChatBot

# 运行服务
python main.py
```

程序启动后会自动：
1. 启动MiVpmClient服务监听语音识别结果
2. 启动Query提取服务处理识别文本
3. 启动AI处理线程进行对话
4. 启动TTS播放器进行语音合成

### 命令行参数

```bash
python main.py [选项]

选项：
  --asr-timeout TIMEOUT    设置ASR超时时间（毫秒），默认5000
  --status-interval SEC    设置状态检查间隔（秒），默认5
  --demo                   运行Query提取服务演示
```

示例：
```bash
# 设置ASR超时为3秒
python main.py --asr-timeout 3000

# 运行演示模式
python main.py --demo
```

## 功能说明

### 内置工具函数

仅作为示例提供，您可以根据需要添加或修改工具函数。

1. **时间查询**：获取当前日期时间
   - 示例："现在几点了？"
   
2. **数学计算**：计算数学表达式
   - 示例："计算 2+2 等于多少"
   - 支持函数：sqrt、sin、cos、tan、log、exp等
   
3. **音量控制**：调整播放音量
   - 示例："音量调大一点"、"把音量调到20"
   - 音量范围：5-35
   
4. **打断播放**：停止当前语音输出
   - 示例："停止说话"

### 自定义配置

您可以在 `main.py` 中修改以下配置：

```python
# AI助手配置
system_prompt = """你是小爱语音助手，热情、乐于助人。请用简洁、口语化的回答"""

# TTS配置
voice = "longhua_v2"  # 可选其他CosyVoice音色
volume = 20          # 默认音量
```

## 项目结构

```
Mi-ChatBot/
├── main.py                    # 主程序入口
├── service.py                 # MiVpmClient服务（监听语音识别）
├── query_extractor.py         # Query提取服务（处理识别文本）
├── cosyvoice_stream_player.py # CosyVoice流式播放器（语音合成）
├── tools.py                   # AI助手工具函数
├── lightweight_tts/           # 轻量级TTS组件目录
├── requirements.txt           # Python依赖列表
├── .env                       # 环境配置文件（需自行创建）
├── .env.example              # 环境配置示例
├── .gitignore                # Git忽略文件
├── LICENSE                   # MIT许可证文件
└── README.md                 # 本文档
```

## 配置开机自启动（可选）

如果您已安装Termux:Boot，可以配置服务开机自启动：

1. **创建启动脚本目录**
   ```bash
   mkdir -p ~/.termux/boot
   ```

2. **创建启动脚本**
   ```bash
   nano ~/.termux/boot/start_mi_chatbot.sh
   ```

3. **编写启动脚本内容**
   ```bash
   #!/data/data/com.termux/files/usr/bin/bash
   # 等待系统启动完成
   sleep 10
   
   # 切换到项目目录
   cd ~/Mi-ChatBot
   
   # 启动AI聊天服务
   python main.py > ~/mi_chatbot.log 2>&1 &
   ```

4. **赋予执行权限**
   ```bash
   chmod +x ~/.termux/boot/start_mi_chatbot.sh
   ```

5. **重启设备测试**
   重启小爱音箱后，服务将自动启动。可以查看日志确认：
   ```bash
   tail -f ~/mi_chatbot.log
   ```

## 注意事项

1. **运行环境**：本服务必须在小爱音箱的Termux终端中运行，不能在其他环境运行
2. **API费用**：使用大语言模型和语音合成API会产生费用，请注意控制使用量
3. **网络要求**：确保设备能够访问相应的API服务
4. **音箱权限**：需要小爱音箱已获得root权限
5. **进程管理**：程序会启动多个子进程，退出时请使用 Ctrl+C 确保所有进程正确关闭
6. **后台运行**：如需后台运行，可以使用 `nohup python main.py &` 或使用 `tmux`/`screen`
7. **Termux:API权限**：首次使用时，Termux:API可能会请求相关权限，请确保授予

## 故障排除

### 常见问题

1. **"请提供API密钥"错误**
   - 确保已正确配置 `.env` 文件
   - 检查环境变量是否正确加载

2. **语音播放无声音**
   - 检查系统音量设置
   - 确认sox播放器已正确安装：`pkg install sox`
   - 使用 `termux-volume` 命令检查音量
   - 确保termux-api已安装：`pkg install termux-api`

3. **ASR无响应**
   - 检查MiVpmClient服务是否正常运行
   - 确认小爱音箱的调试接口是否开启
   - 检查是否在Termux环境中运行

4. **TTS合成失败**
   - 检查阿里云API密钥是否有效
   - 确认账户余额充足
   - 检查网络连接

5. **Termux权限问题**
   - 确保Termux有存储权限：`termux-setup-storage`
   - 如遇到权限错误，尝试使用 `su` 命令获取root权限
   
6. **音量控制失败**
   - 确保已安装Termux:API应用
   - 检查termux-api包是否已安装：`pkg install termux-api`
   - 首次使用时授予Termux:API所需的系统权限
   
7. **开机自启动不工作**
   - 确保已安装Termux:Boot应用
   - 检查启动脚本路径是否正确：`~/.termux/boot/`
   - 确认脚本有执行权限：`ls -la ~/.termux/boot/`

### 日志查看

程序运行时会输出详细的日志信息，包括：
- 服务启动状态
- ASR识别结果
- AI对话内容
- TTS合成状态
- 错误信息

## 扩展开发

### 添加新的工具函数

在 `tools.py` 中添加新函数，然后在 `main.py` 的 `_register_tools` 方法中注册：

```python
# tools.py
def my_custom_tool(param: str) -> str:
    """自定义工具函数"""
    return f"处理结果: {param}"

# main.py
self.agent.register_tool(my_custom_tool, name="自定义工具")
```

### 更换大语言模型

修改 `.env` 中的配置即可切换到其他兼容OpenAI API格式的模型：

```env
BASE_URL=https://api.anthropic.com/v1  # 例如Claude
MODEL_NAME=claude-3-sonnet
API_KEY=your_claude_api_key
```

## 许可证

本项目采用 MIT License 许可证。详见 [LICENSE](LICENSE) 文件。

## 免责声明

**重要提示**：
- 本项目仅供学习和研究使用
- 使用本项目需要您自行承担所有风险
- 本项目不对因使用本软件造成的任何损失负责
- 请确保您的使用符合当地法律法规
- 本项目与小米公司无任何关联

本软件按"原样"提供，不提供任何形式的保证。作者不对因使用本软件而产生的任何直接或间接损失承担责任。

## 贡献

欢迎提交Issue和Pull Request！

## 联系方式

