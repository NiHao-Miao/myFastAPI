"""工具结果中的隐藏来源标记。

工具把结构化来源附在文本末尾；middleware 会解析并从返回给模型的
ToolMessage 中移除，模型只看到干净的自然语言内容。
"""

SOURCE_MARKER = "\n[[SOURCES]]"
