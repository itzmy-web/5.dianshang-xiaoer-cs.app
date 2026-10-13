condition = "__import__('os').system('del important_file.txt')"
data = {"slots": {}}

# 禁止执行内部函数
result = eval(condition, {'__builtins__': None}, data)
# ❌ 报错！
# 因为全局变量字典被禁用，__import__ 这个函数不存在
