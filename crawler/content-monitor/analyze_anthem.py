import dashscope
from dashscope import MultiModalConversation
import base64
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

dashscope.api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
if not dashscope.api_key:
    raise RuntimeError("缺少环境变量 DASHSCOPE_API_KEY")

images = [
    ("0:00:30", "maker_00_00_30.jpg"),
    ("0:05:00", "maker_00_05_00.jpg"),
    ("0:15:00", "maker_00_15_00.jpg"),
    ("0:30:00", "maker_00_30_00.jpg"),
    ("0:45:00", "maker_00_45_00.jpg"),
    ("1:00:00", "maker_01_00_00.jpg"),
    ("1:30:00", "maker_01_30_00.jpg"),
    ("2:00:00", "maker_02_00_00.jpg"),
    ("2:30:00", "maker_02_30_00.jpg"),
    ("2:50:00", "maker_02_50_00.jpg"),
    ("3:00:00", "maker_03_00_00.jpg"),
    ("3:10:00", "maker_03_10_00.jpg"),
    ("3:20:00", "maker_03_20_00.jpg"),
    ("3:30:00", "maker_03_30_00.jpg"),
    ("3:37:00", "maker_03_37_00.jpg"),
]

base_dir = r"D:\project\content-monitor\video_outputs\anthem"

for time_str, filename in images:
    image_path = os.path.join(base_dir, filename)

    # 读取图片并转为 base64
    with open(image_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode("utf-8")
    image_b64 = f"data:image/jpeg;base64,{img_data}"

    messages = [
        {
            "role": "user",
            "content": [
                {"image": image_b64},
                {"text": (
                    "请详细描述这张图片的内容，重点回答以下几点：\n"
                    "1. 是否是游戏画面？如果是，是哪款游戏？画面里在发生什么？\n"
                    "2. 是否是人物讲话/出镜画面（真人或虚拟主播）？\n"
                    "3. 画面中有哪些可见文字（标题、字幕、UI文字等）？\n"
                    "4. 画面整体主题/场景是什么？\n"
                    "请用中文回答，尽量详细。"
                )}
            ]
        }
    ]
    try:
        response = MultiModalConversation.call(model="qwen-vl-plus", messages=messages)
        result = response.output.choices[0].message.content[0]["text"]
    except Exception as e:
        result = f"【调用失败】{e}"

    print(f"时间点: {time_str}")
    print(f"画面内容: {result}")
    print("-" * 60)
