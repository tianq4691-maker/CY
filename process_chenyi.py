import pandas as pd
from collections import defaultdict

# ── 1. 读取并排序 ──────────────────────────────────────────────────────────────
df = pd.read_excel('陈毅生平事件摘要.xlsx')
df['*起始日期（YYYY/MM/DD）'] = pd.to_datetime(df['*起始日期（YYYY/MM/DD）'], errors='coerce')

# 按起始日期升序排列，空日期放最后
df_sorted = df.sort_values('*起始日期（YYYY/MM/DD）', ascending=True, na_position='last').reset_index(drop=True)
df_sorted.to_csv('陈毅生平事件摘要_按开始时间重排序.csv', index=False, encoding='utf-8-sig')
print(f'排序完成，共 {len(df_sorted)} 行')

# ── 2. 定义五个阶段的时间区间 ─────────────────────────────────────────────────
stages = [
    ('第1阶段', '1901-08-26', '1923-11-01'),
    ('第2阶段', '1923-11-02', '1937-09-29'),
    ('第3阶段', '1937-09-30', '1945-10-25'),
    ('第4阶段', '1945-10-26', '1949-05-27'),
    # 延伸至1972-01-31，以包含陈毅逝世后追悼会等相关事件（1972-01-10）
    ('第5阶段', '1949-05-28', '1972-01-31'),
]

# ── 3. 拆分并保存各阶段 CSV ────────────────────────────────────────────────────
def split_stages(df, stages):
    results = {}
    for name, start, end in stages:
        s = pd.Timestamp(start)
        e = pd.Timestamp(end)
        mask = (
            (df['*起始日期（YYYY/MM/DD）'] >= s) &
            (df['*起始日期（YYYY/MM/DD）'] <= e)
        )
        # 空日期行归入最后阶段或跳过
        stage_df = df[mask].copy().reset_index(drop=True)
        results[name] = stage_df
        stage_df.to_csv(f'{name}.csv', index=False, encoding='utf-8-sig')
        print(f'{name}: {len(stage_df)} 行  ({start} ~ {end})')
    return results

stage_data = split_stages(df_sorted, stages)

# 检查未被覆盖的行
covered = set()
for name, start, end in stages:
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    covered |= set(df_sorted[
        (df_sorted['*起始日期（YYYY/MM/DD）'] >= s) &
        (df_sorted['*起始日期（YYYY/MM/DD）'] <= e)
    ].index)
uncovered = df_sorted[~df_sorted.index.isin(covered)]
print(f'\n未被阶段覆盖的行（空日期或越界）: {len(uncovered)}')
if len(uncovered) > 0:
    print(uncovered[['*起始日期（YYYY/MM/DD）', '*事件名【主体名+动词+客体名（地点名）】']].to_string())
    # 将无日期的行追加到第5阶段
    nat_rows = uncovered[uncovered['*起始日期（YYYY/MM/DD）'].isna()]
    if len(nat_rows) > 0:
        print(f'\n无日期行 ({len(nat_rows)} 条) 将追加至第5阶段')
        stage_data['第5阶段'] = pd.concat([stage_data['第5阶段'], nat_rows], ignore_index=True)
        stage_data['第5阶段'].to_csv('第5阶段.csv', index=False, encoding='utf-8-sig')

# ── 4. 构建 Node & Edge 文件 ───────────────────────────────────────────────────
def is_person(name):
    """简单过滤：排除明显的组织/机构名称，保留人物"""
    if not isinstance(name, str) or not name.strip():
        return False
    name = name.strip()
    # 排除空值
    if name in ('nan', 'NaN', ''):
        return False
    return True

def build_node_edge(stage_df, stage_name):
    source_col = '*主体人物/组织'
    target_col = '客体人物/组织'

    # 收集所有出现的实体
    all_entities = set()
    for val in stage_df[source_col].dropna():
        v = str(val).strip()
        if is_person(v):
            all_entities.add(v)
    for val in stage_df[target_col].dropna():
        v = str(val).strip()
        if is_person(v):
            all_entities.add(v)

    # 构建 node 文件（按首次出现顺序编号）
    entity_order = []
    seen = set()
    for _, row in stage_df.iterrows():
        for col in [source_col, target_col]:
            val = row[col]
            if pd.isna(val):
                continue
            v = str(val).strip()
            if is_person(v) and v not in seen:
                entity_order.append(v)
                seen.add(v)

    node_df = pd.DataFrame({
        '序号': range(1, len(entity_order) + 1),
        'label': entity_order
    })
    node_df.to_csv(f'{stage_name} node.csv', index=False, encoding='utf-8-sig')

    # 构建 edge 文件：统计 (source, target) 出现频次
    edge_counter = defaultdict(int)
    for _, row in stage_df.iterrows():
        src = row[source_col]
        tgt = row[target_col]
        if pd.isna(src) or pd.isna(tgt):
            continue
        src = str(src).strip()
        tgt = str(tgt).strip()
        if is_person(src) and is_person(tgt):
            edge_counter[(src, tgt)] += 1

    if edge_counter:
        edge_rows = [
            {'Source': s, 'Target': t, 'Type': 'Directed', 'Weight': w}
            for (s, t), w in sorted(edge_counter.items(), key=lambda x: -x[1])
        ]
        edge_df = pd.DataFrame(edge_rows)
    else:
        edge_df = pd.DataFrame(columns=['Source', 'Target', 'Type', 'Weight'])

    edge_df.to_csv(f'{stage_name} edge.csv', index=False, encoding='utf-8-sig')

    print(f'{stage_name}: {len(node_df)} 个节点, {len(edge_df)} 条边')
    return node_df, edge_df

print('\n=== 构建 Node & Edge 文件 ===')
for name, start, end in stages:
    build_node_edge(stage_data[name], name)

print('\n全部处理完成！')
