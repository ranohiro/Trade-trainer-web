import re

with open('app.py', 'r') as f:
    content = f.read()

# Find the draw_candlestick definition block
func_start = content.find("        def draw_candlestick(df, title, trade_history=None, signal_history=None):")

if func_start == -1:
    print("Function start not found")
    exit(1)

# Find the return fig
func_end = content.find("            return fig", func_start) + len("            return fig")
end_of_line = content.find("\n", func_end)
if end_of_line != -1:
    func_end = end_of_line + 1

func_body = content[func_start:func_end]

# Remove it from its current position
content = content.replace(func_body, "")

# Dedent by 4 spaces
dedented_body = "\n".join(line[4:] if line.startswith("    ") else line for line in func_body.split("\n"))

# Find where to insert it (after calculate_max_drawdown)
insert_target = "        return max_drawdown\n"
insert_pos = content.find(insert_target) + len(insert_target)

# Insert the dedented function
content = content[:insert_pos] + "\n" + dedented_body + content[insert_pos:]

with open('app.py', 'w') as f:
    f.write(content)

print("Fix applied successfully")
