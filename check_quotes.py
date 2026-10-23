content = open('blog_posts.py', 'r', encoding='utf-8').read()
idx = 0
count = 0
positions = []
while True:
    idx = content.find('"""', idx)
    if idx == -1:
        break
    line_num = content[:idx].count('\n') + 1
    positions.append((line_num, content[max(0,idx-30):idx+30]))
    idx += 3
    count += 1

print(f'Total triple-quotes: {count}')
for ln, ctx in positions:
    print(f'  Line {ln}: ...{repr(ctx)}...')
