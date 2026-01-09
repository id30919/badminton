import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import math
import random
import json
import io
import re
from datetime import datetime, timedelta, time

# 設定頁面寬度
st.set_page_config(layout="wide", page_title="熊德盃賽事規劃系統 v4.6")

# --- CSS 優化 ---
st.markdown("""
<style>
    .stDataFrame {font-size: 1.1rem;}
    div[data-testid="stMetricValue"] {font-size: 1.8rem;}
    th {text-align: center !important;}
    td {text-align: center !important; white-space: pre-wrap !important;}
</style>
""", unsafe_allow_html=True)

# --- Session State 初始化 ---
if 'teams' not in st.session_state:
    st.session_state.teams = []
if 'matches' not in st.session_state:
    st.session_state.matches = []
if 'schedule' not in st.session_state:
    st.session_state.schedule = None
if 'schedule_list' not in st.session_state:
    st.session_state.schedule_list = [] 

# --- 顏色定義 ---
COLOR_PALETTE = [
    '#FFCDD2', '#C8E6C9', '#BBDEFB', '#FFF9C4', 
    '#E1BEE7', '#FFE0B2', '#B2DFDB', '#F0F4C3'
]

def get_group_color_hex(level_name, all_levels):
    try:
        if "決賽" in level_name or "總冠軍" in level_name: return '#FF8A80'
        if "季殿" in level_name: return '#FFD180'
        if "敗部" in level_name: return '#EA80FC'
        
        normal_levels = [l for l in all_levels if "決賽" not in l and "敗部" not in l]
        if level_name in normal_levels:
            idx = normal_levels.index(level_name) % len(COLOR_PALETTE)
            return COLOR_PALETTE[idx]
        return '#FFFFFF'
    except:
        return '#FFFFFF'

# --- 核心功能：HTML/CSS 手繪樹狀圖 (直角無箭頭) ---
def render_custom_bracket(final_match, sub_matches, title, icon):
    """
    使用 CSS Flexbox 繪製標準的 1對2 樹狀圖
    """
    # 準備資料
    if not final_match:
        return f"<div style='padding:20px;'>尚無 {title} 資料</div>"
        
    top_node_html = f"""
    <div class="match-box final-box">
        <div class="match-no">Match No.{final_match['match_no']} {icon}</div>
        <div class="match-desc">{final_match['desc']}</div>
        <div class="match-teams">{final_match['team_a']} <br>vs<br> {final_match['team_b']}</div>
    </div>
    """
    
    bottom_nodes_html = ""
    # 如果有下層比賽 (來源比賽)，且數量為 2 (剛好畫成樹狀)
    # 如果數量不夠，就用 placeholder 補
    children = sub_matches[:2]
    
    # 確保有兩個子節點位置，為了排版對稱
    if len(children) == 0:
        # 如果沒有下層比賽 (例如季軍賽通常沒有直接的前置賽事編號，是輸的過來)，顯示「敗方」資訊
        bottom_nodes_html = f"""
        <div class="child-wrapper">
            <div class="match-box sub-box placeholder">
                4強賽 敗方1
            </div>
        </div>
        <div class="child-wrapper">
            <div class="match-box sub-box placeholder">
                4強賽 敗方2
            </div>
        </div>
        """
    elif len(children) == 1:
         # 只有一場? 雖然罕見但防呆
         m = children[0]
         bottom_nodes_html = f"""
        <div class="child-wrapper">
            <div class="match-box sub-box">
                <div class="match-no">No.{m['match_no']}</div>
                <div class="match-desc">{m['desc']}</div>
                <div class="match-teams">{m['team_a']} vs {m['team_b']}</div>
            </div>
        </div>
        <div class="child-wrapper"></div>
        """
    else:
        # 正常兩場
        for m in children:
            bottom_nodes_html += f"""
            <div class="child-wrapper">
                <div class="match-box sub-box">
                    <div class="match-no">No.{m['match_no']}</div>
                    <div class="match-desc">{m['desc']}</div>
                    <div class="match-teams">{m['team_a']} <br>vs<br> {m['team_b']}</div>
                </div>
            </div>
            """

    # HTML 結構：利用 CSS 畫線
    html = f"""
    <div class="bracket-group">
        <div class="group-title">{title}</div>
        <div class="tree-structure">
            <!-- 上層 -->
            <div class="level-1">
                {top_node_html}
            </div>
            <!-- 連接線區 -->
            <div class="connector-lines">
                <div class="line-vertical-top"></div>
                <div class="line-horizontal"></div>
                <div class="line-vertical-bottom-left"></div>
                <div class="line-vertical-bottom-right"></div>
            </div>
            <!-- 下層 -->
            <div class="level-2">
                {bottom_nodes_html}
            </div>
        </div>
    </div>
    """
    return html

def render_all_brackets(schedule_list):
    # 1. 篩選資料
    # 總冠軍
    gold_final = next((m for m in schedule_list if "總冠軍" in m['desc']), None)
    # 4強 (勝部)
    semi_finals = [m for m in schedule_list if "4強" in m['desc'] and "敗部" not in m['desc']]
    
    # 敗部冠軍
    loser_final = next((m for m in schedule_list if "敗部冠軍" in m['desc']), None)
    # 敗部4強
    loser_semis = [m for m in schedule_list if "敗部4強" in m['desc']]
    
    # 季軍賽
    bronze_final = next((m for m in schedule_list if "季殿" in m['desc']), None)
    # 季軍賽的來源是4強的敗方，通常沒有獨立的 "match no"，所以這部分僅顯示樹狀結構的尾端
    # 這裡我們傳入空 list，讓 render 函數畫出 placeholder
    bronze_sources = [] 

    # CSS 樣式表
    css = """
    <style>
        .container {
            display: flex;
            justify-content: space-around;
            flex-wrap: wrap;
            font-family: sans-serif;
            background-color: #f9f9f9;
            padding: 20px;
        }
        .bracket-group {
            background-color: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            margin: 10px;
            min-width: 300px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .group-title {
            text-align: center;
            font-weight: bold;
            font-size: 1.2em;
            margin-bottom: 20px;
            color: #333;
            border-bottom: 2px solid #eee;
            padding-bottom: 10px;
        }
        .tree-structure {
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .match-box {
            border: 2px solid #FFC107; /* 黃色邊框 */
            background-color: #FFF9C4; /* 淺黃底 */
            padding: 8px;
            text-align: center;
            border-radius: 4px;
            width: 180px;
            position: relative;
            z-index: 2;
        }
        .final-box {
            font-weight: bold;
            background-color: #FFF176;
        }
        .sub-box {
            font-size: 0.9em;
        }
        .placeholder {
            border: 2px dashed #ccc;
            background-color: #eee;
            color: #777;
        }
        .match-no { font-size: 0.8em; color: #555; margin-bottom: 2px; }
        .match-desc { font-weight: bold; margin-bottom: 4px; }
        .match-teams { font-size: 0.9em; }
        
        /* 線條魔法 */
        .connector-lines {
            position: relative;
            height: 30px; /* 線條區高度 */
            width: 100%;
            margin-bottom: 0;
        }
        .line-vertical-top {
            position: absolute;
            left: 50%;
            top: 0;
            height: 15px; /* 上半段長度 */
            width: 2px;
            background-color: #333;
            transform: translateX(-50%);
        }
        .line-horizontal {
            position: absolute;
            top: 15px; /* 橫線位置 = top線長度 */
            left: 25%; /* 從左邊 1/4 處開始 */
            width: 50%; /* 寬度佔一半 */
            height: 2px;
            background-color: #333;
        }
        /* 特別處理：如果有兩個子節點，橫線才需要。這裡簡化假設都有 */
        
        .line-vertical-bottom-left {
            position: absolute;
            top: 15px;
            left: 25%;
            height: 15px;
            width: 2px;
            background-color: #333;
        }
        .line-vertical-bottom-right {
            position: absolute;
            top: 15px;
            right: 25%;
            height: 15px;
            width: 2px;
            background-color: #333;
        }

        .level-2 {
            display: flex;
            justify-content: space-between;
            width: 100%;
            gap: 20px;
        }
        .child-wrapper {
            flex: 1;
            display: flex;
            justify-content: center;
        }
    </style>
    """
    
    html_content = f"""
    {css}
    <div class="container">
        {render_custom_bracket(gold_final, semi_finals, "🏆 總冠軍賽程", "🥇")}
        {render_custom_bracket(loser_final, loser_semis, "🛡️ 敗部冠軍賽程", "🛡️")}
        {render_custom_bracket(bronze_final, bronze_sources, "🥉 季殿軍賽程", "🥉")}
    </div>
    """
    
    components.html(html_content, height=600, scrolling=True)


# --- 側邊欄設定 ---
st.sidebar.title("🏆 熊德盃設定面板")
is_guest_mode = st.sidebar.checkbox("開啟訪客檢視模式", value=False)

with st.sidebar.expander("1. 時間與場地設定", expanded=not is_guest_mode):
    start_time = st.time_input("租借開始時間", time(9, 0))
    end_time = st.time_input("租借結束時間", time(18, 0))
    setup_teardown_min = st.number_input("佈置/頒獎預留 (前後各扣除分鐘)", 0, 120, 60)
    
    st.markdown("---")
    st.markdown("#### 🏸 賽制與點數設定")
    num_courts = st.number_input("可用場地數量", 1, 20, 10)
    mins_per_point = st.number_input("每點(每局) 時間 (分鐘)", 5, 30, 15)
    points_per_matchup = st.number_input("每場對戰打幾點?", 1, 7, 5)
    
    total_matchup_duration = mins_per_point * points_per_matchup
    st.info(f"ℹ️ 一場對戰佔用: {total_matchup_duration} 分鐘 ({points_per_matchup} 格)")

if not is_guest_mode:
    with st.sidebar.expander("2. 費用與資源估算"):
        shuttles_per_point = st.number_input("每點(每局)使用球數", 1, 6, 2)
        shuttle_tube_price = st.number_input("每桶球價格 ($)", 0, 2000, 950)
        court_price_per_hr = st.number_input("場地費/面/時 ($)", 0, 2000, 500)
        medal_price = st.number_input("獎牌費/人 ($)", 0, 1000, 200)
        food_price = st.number_input("熱炒費/人 ($)", 0, 2000, 500)
        players_per_team = st.number_input("每隊人數", 1, 20, 6)
        st.markdown("---")
        staff_count = st.number_input("工作人員人數", 0, 50, 5)
        staff_fee = st.number_input("工作人員費用/人 ($)", 0, 5000, 1000)

    with st.sidebar.expander("3. 檔案存取"):
        def convert_to_json():
            data = {"teams": st.session_state.teams, "matches": st.session_state.matches}
            return json.dumps(data, ensure_ascii=False)
        json_data = convert_to_json()
        st.download_button("💾 下載設定檔 (JSON)", json_data, "badminton_config.json", "application/json")
        uploaded_file = st.file_uploader("📂 上傳設定檔")
        if uploaded_file is not None:
            try:
                data = json.load(uploaded_file)
                st.session_state.teams = data.get("teams", [])
                st.session_state.matches = data.get("matches", [])
                st.success("✅ 讀取成功！")
            except:
                st.error("讀取失敗")

# --- 優先級邏輯 ---
def get_match_priority(match):
    m_type = match.get("type", "")
    desc = match.get("desc", "")
    if "初賽" in m_type: return 0
    elif "總冠軍" in desc: return 4
    elif "季殿軍" in desc: return 3
    elif "敗部冠軍" in desc: return 2
    elif "複賽" in m_type: return 1
    return 1

def sort_matches_by_priority():
    if st.session_state.matches:
        st.session_state.matches.sort(key=get_match_priority)

# --- 主畫面 ---
st.title("🏸 熊德盃羽球比賽 賽制規劃/查詢系統 v4.6")

if is_guest_mode:
    tabs = st.tabs(["賽程查詢與排程", "樹狀圖與名次"])
else:
    tabs = st.tabs(["1. 報名與分組", "2. 賽制產生器", "3. 排程與查詢", "4. 樹狀圖與名次", "5. 預算試算"])

# ==========================================
# Tab 1: 報名
# ==========================================
if not is_guest_mode:
    with tabs[0]:
        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("新增隊伍")
            new_team = st.text_input("輸入隊名")
            manual_level = st.selectbox("指定組別", ["A組", "B組", "C組", "D組", "未分組"])
            if st.button("新增單一隊伍"):
                if new_team:
                    st.session_state.teams.append({"name": new_team, "level": manual_level})
                    st.success(f"已新增 {new_team}")

            st.divider()
            test_count = st.number_input("生成數量", 1, 50, 8)
            if st.button("⚡ 一鍵生成測試隊伍"):
                adjectives = ["無敵", "快樂", "爆汗", "光速", "黃金", "超級", "肉腳", "佛系"]
                nouns = ["暴龍", "羽球團", "小隊", "殺球隊", "戰隊", "俱樂部", "聯隊"]
                for i in range(test_count):
                    name = f"{random.choice(adjectives)}{random.choice(nouns)}-{i+1:02d}"
                    st.session_state.teams.append({"name": name, "level": "未分組"})
                st.success(f"已生成 {test_count} 隊")
                st.rerun()
            if st.button("🗑️ 清空所有隊伍"):
                st.session_state.teams = []
                st.rerun()
        with col2:
            st.subheader(f"隊伍清單 (共 {len(st.session_state.teams)} 隊)")
            with st.expander("⚖️ 自動平衡分組工具", expanded=True):
                target_groups = st.number_input("希望分成幾組？", 2, 8, 2)
                group_names = ["A組", "B組", "C組", "D組", "E組", "F組", "G組", "H組"]
                if st.button("🚀 執行亂數分組"):
                    if not st.session_state.teams:
                        st.error("沒有隊伍可以分組")
                    else:
                        random.shuffle(st.session_state.teams)
                        for i, team in enumerate(st.session_state.teams):
                            grp_idx = i % target_groups
                            team['level'] = group_names[grp_idx]
                        st.success(f"已分組完成！")
                        st.rerun()
            if st.session_state.teams:
                df_teams = pd.DataFrame(st.session_state.teams)
                df_teams.index = df_teams.index + 1
                st.dataframe(df_teams, use_container_width=True)

# ==========================================
# Tab 2: 賽制
# ==========================================
if not is_guest_mode:
    with tabs[1]:
        st.subheader("建立對戰組合")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🔹 第一階段：分組循環賽")
            if st.button("產生【初賽】循環賽程"):
                st.session_state.matches = [] 
                levels = sorted(list(set(t['level'] for t in st.session_state.teams)))
                count = 0
                for lvl in levels:
                    if lvl == "未分組": continue
                    lvl_teams = [t for t in st.session_state.teams if t['level'] == lvl]
                    n = len(lvl_teams)
                    for i in range(n):
                        for j in range(i + 1, n):
                            st.session_state.matches.append({
                                "type": "初賽",
                                "level": lvl,
                                "team_a": lvl_teams[i]['name'],
                                "team_b": lvl_teams[j]['name'],
                                "desc": f"{lvl} 循環賽"
                            })
                            count += 1
                sort_matches_by_priority()
                if count > 0: st.success(f"已新增 {count} 場初賽！")
                else: st.warning("請先分組。")

        with c2:
            st.markdown("### 🔸 第二階段：複賽 & 決賽")
            col_a, col_b = st.columns(2)
            group_1 = col_a.selectbox("對戰群組 1", ["A組", "B組", "C組", "D組"], index=0)
            group_2 = col_b.selectbox("對戰群組 2", ["A組", "B組", "C組", "D組"], index=1)
            include_loser = st.checkbox("包含敗部賽程", value=True)
            
            if st.button("產生【複賽/決賽】對戰"):
                match_sf1 = {"type": "複賽-勝部", "level": "決賽區", "team_a": f"{group_1} 冠軍", "team_b": f"{group_2} 亞軍", "desc": "4強賽 A1vsB2"}
                match_sf2 = {"type": "複賽-勝部", "level": "決賽區", "team_a": f"{group_2} 冠軍", "team_b": f"{group_1} 亞軍", "desc": "4強賽 B1vsA2"}
                st.session_state.matches.extend([match_sf1, match_sf2])
                
                if include_loser:
                    match_ls1 = {"type": "複賽-敗部", "level": "敗部區", "team_a": f"{group_1} 季軍", "team_b": f"{group_2} 殿軍", "desc": "敗部4強 A3vsB4"}
                    match_ls2 = {"type": "複賽-敗部", "level": "敗部區", "team_a": f"{group_2} 季軍", "team_b": f"{group_1} 殿軍", "desc": "敗部4強 B3vsA4"}
                    match_l_final = {"type": "決賽-敗部", "level": "敗部區", "team_a": "敗部4強 勝方1", "team_b": "敗部4強 勝方2", "desc": "🛡️ 敗部冠軍賽"}
                    st.session_state.matches.extend([match_ls1, match_ls2, match_l_final])
                
                match_bronze = {"type": "決賽-勝部", "level": "決賽區", "team_a": "4強賽 敗方1", "team_b": "4強賽 敗方2", "desc": "🥉 季殿軍賽"}
                match_gold = {"type": "決賽-勝部", "level": "決賽區", "team_a": "4強賽 勝方1", "team_b": "4強賽 勝方2", "desc": "🏆 總冠軍賽"}
                st.session_state.matches.extend([match_bronze, match_gold])
                
                sort_matches_by_priority()
                st.success("已新增決賽賽程！")

        st.divider()
        if st.button("⚠️ 清空賽程"):
            st.session_state.matches = []
            st.rerun()
            
        df_matches = pd.DataFrame(st.session_state.matches)
        if not df_matches.empty:
            df_matches.index = df_matches.index + 1
            st.dataframe(df_matches, use_container_width=True)

# ==========================================
# Tab 3: 排程 (賽程大表)
# ==========================================
schedule_tab_idx = 0 if is_guest_mode else 2
with tabs[schedule_tab_idx]:
    st.subheader("排程系統 (賽程大表)")
    
    t_start = datetime.combine(datetime.today(), start_time)
    t_end = datetime.combine(datetime.today(), end_time)
    play_start = t_start + timedelta(minutes=setup_teardown_min)
    play_end = t_end - timedelta(minutes=setup_teardown_min)
    total_play_minutes = (play_end - play_start).total_seconds() / 60
    slots_count = int(total_play_minutes // mins_per_point)
    
    # 搜尋框
    c_filter, _ = st.columns([2, 2])
    with c_filter:
        team_list = ["無"] + [t['name'] for t in st.session_state.teams]
        team_list += ["A組", "B組", "C組", "D組", "冠軍", "季軍"]
        filter_team = st.selectbox("🔍 搜尋隊伍 (高亮顯示)", team_list)

    if not is_guest_mode:
        if st.button("🚀 開始排程 (生成大表)"):
            if not st.session_state.matches:
                st.error("無賽程資料")
            else:
                sort_matches_by_priority()
                
                schedule_grid = [["" for _ in range(num_courts)] for _ in range(slots_count)]
                grid_meta = [[None for _ in range(num_courts)] for _ in range(slots_count)]
                match_queue = st.session_state.matches.copy()
                team_busy_until = {} 
                scheduled_matches_list = []

                for row in range(slots_count):
                    if row + points_per_matchup > slots_count: break
                    if match_queue:
                         match_queue.sort(key=get_match_priority)
                         min_p = min(get_match_priority(m) for m in match_queue)
                    else:
                        min_p = 999

                    for col in range(num_courts):
                        if not match_queue: break
                        if schedule_grid[row][col] != "": continue
                            
                        found_match_idx = -1
                        for idx, match in enumerate(match_queue):
                            if get_match_priority(match) > min_p: continue
                            ta, tb = match['team_a'], match['team_b']
                            if not (row < team_busy_until.get(ta, -1) or row < team_busy_until.get(tb, -1)):
                                found_match_idx = idx
                                break
                        
                        if found_match_idx != -1:
                            match = match_queue.pop(found_match_idx)
                            end_row = row + points_per_matchup
                            
                            for r in range(row, end_row):
                                schedule_grid[r][col] = "OCCUPIED"
                                grid_meta[r][col] = match
                            
                            team_busy_until[match['team_a']] = end_row
                            team_busy_until[match['team_b']] = end_row
                            
                            if match_queue:
                                min_p = min(get_match_priority(m) for m in match_queue)

                global_match_counter = 1
                final_schedule_grid = [["" for _ in range(num_courts)] for _ in range(slots_count)]
                
                for row in range(slots_count):
                    for col in range(num_courts):
                        match_info = grid_meta[row][col]
                        if match_info:
                            current_no = global_match_counter
                            global_match_counter += 1
                            
                            is_head = False
                            if row == 0: is_head = True
                            elif grid_meta[row-1][col] != match_info: is_head = True
                            
                            if is_head:
                                cell_text = f"No.{current_no}\n{match_info['team_a']}\nvs\n{match_info['team_b']}\n({match_info['level']})"
                                if 'start_no' not in match_info:
                                    match_info['start_no'] = current_no
                            else:
                                cell_text = f"No.{current_no} ..."
                            
                            final_schedule_grid[row][col] = cell_text
                            
                            if is_head:
                                export_item = match_info.copy()
                                export_item['match_no'] = current_no
                                export_item['time'] = (play_start + timedelta(minutes=row*mins_per_point)).strftime("%H:%M")
                                scheduled_matches_list.append(export_item)

                time_labels = []
                for i in range(slots_count):
                    t = play_start + timedelta(minutes=i*mins_per_point)
                    time_labels.append(t.strftime("%H:%M"))
                col_labels = [f"Court {i+1}" for i in range(num_courts)]
                
                st.session_state.schedule = pd.DataFrame(final_schedule_grid, index=time_labels, columns=col_labels)
                st.session_state.schedule_list = scheduled_matches_list
                
                if match_queue:
                    st.warning(f"⚠️ 尚有 {len(match_queue)} 場排不進去")
                else:
                    st.success("✅ 賽程大表生成完畢！")

    if st.session_state.schedule is not None:
        st.divider()
        all_match_levels = []
        if st.session_state.schedule_list:
            all_match_levels = sorted(list(set(m['level'] for m in st.session_state.schedule_list)))

        def style_schedule_cells(val):
            val_str = str(val)
            if not val_str: return ''
            if filter_team != "無" and filter_team in val_str:
                return 'background-color: #ffeb3b; color: black; font-weight: bold; border: 2px solid red;'
            if "..." in val_str:
                 return 'background-color: #f5f5f5; color: #aaa;'

            bg_color = '#FFFFFF'
            try:
                if "總冠軍" in val_str: bg_color = '#FF8A80'
                elif "季殿" in val_str: bg_color = '#FFD180'
                elif "敗部" in val_str: bg_color = '#EA80FC'
                elif "決賽" in val_str: bg_color = '#FF8A80'
                else:
                    found_level = None
                    for lvl in all_match_levels:
                        if lvl in val_str:
                            found_level = lvl
                            break
                    if found_level:
                        bg_color = get_group_color_hex(found_level, all_match_levels)
            except:
                pass
            return f'background-color: {bg_color}; color: black;'

        st.write("🎨 **組別色碼圖例**：")
        cols = st.columns(8)
        legend_levels = [l for l in all_match_levels if "決賽" not in l and "敗部" not in l]
        for i, level in enumerate(legend_levels):
            c = get_group_color_hex(level, all_match_levels)
            cols[i % 8].markdown(f"<div style='background-color:{c};padding:5px;border-radius:5px;text-align:center'>{level}</div>", unsafe_allow_html=True)
        st.write("")

        st.dataframe(
            st.session_state.schedule.style.applymap(style_schedule_cells),
            height=800,
            use_container_width=True
        )
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            st.session_state.schedule.to_excel(writer, sheet_name='賽程大表')
            df_list = pd.DataFrame(st.session_state.schedule_list)
            if not df_list.empty:
                df_list = df_list[['match_no', 'time', 'level', 'team_a', 'team_b', 'desc']]
                df_list.to_excel(writer, sheet_name='對戰清單')
        
        st.download_button(
            label="📥 一鍵下載 Excel",
            data=buffer.getvalue(),
            file_name="badminton_master_schedule.xlsx",
            mime="application/vnd.ms-excel"
        )

# ==========================================
# Tab 4: 樹狀圖 (HTML/CSS 客製版)
# ==========================================
tree_tab_idx = 1 if is_guest_mode else 3
with tabs[tree_tab_idx]:
    st.subheader("🏆 晉級樹狀圖 (Brackets)")
    
    if not st.session_state.schedule_list:
        st.info("請先在「排程」頁面完成排程。")
    else:
        schedule_list = st.session_state.schedule_list
        render_all_brackets(schedule_list) # 呼叫新函數

        st.divider()
        st.info("👇 下方表格可直接複製到 Google Sheets (填分用)")
        
        # 篩選出決賽/複賽資料
        bracket_matches = [m for m in schedule_list if "決賽" in m['type'] or "複賽" in m['type']]
        bracket_matches.sort(key=lambda x: x['match_no'])
        
        bracket_data = []
        for m in bracket_matches:
            bracket_data.append({
                "Match No.": m['match_no'],
                "Stage": m['desc'],
                "Team A": m['team_a'],
                "Score A": "",
                "Score B": "",
                "Team B": m['team_b'],
                "Next Match": " (自行填寫)" 
            })
        df_bracket = pd.DataFrame(bracket_data)
        st.dataframe(df_bracket, use_container_width=True)

        buffer_bracket = io.BytesIO()
        with pd.ExcelWriter(buffer_bracket, engine='openpyxl') as writer:
            df_bracket.to_excel(writer, sheet_name='樹狀圖填分表', index=False)
                
        st.download_button(
            label="📥 下載填分表 (Excel)",
            data=buffer_bracket.getvalue(),
            file_name="tournament_brackets.xlsx",
            mime="application/vnd.ms-excel"
        )

# ==========================================
# Tab 5: 預算
# ==========================================
if not is_guest_mode:
    with tabs[4]:
        st.subheader("💰 經費預算表")
        if not st.session_state.teams:
            st.warning("請先新增隊伍")
        else:
            total_teams = len(st.session_state.teams)
            total_players = total_teams * players_per_team
            total_matches = len(st.session_state.matches)
            rent_hours = (datetime.combine(datetime.today(), end_time) - datetime.combine(datetime.today(), start_time)).total_seconds() / 3600
            
            cost_court = num_courts * rent_hours * court_price_per_hr
            total_shuttles = total_matches * points_per_matchup * shuttles_per_point
            tubes_needed = math.ceil(total_shuttles / 12)
            cost_shuttles = tubes_needed * shuttle_tube_price
            cost_medals = total_players * medal_price
            cost_food = total_players * food_price
            cost_staff = staff_count * staff_fee
            
            total_cost = cost_court + cost_shuttles + cost_medals + cost_food + cost_staff
            
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("總參賽人數", f"{total_players} 人")
                st.metric("工作人員", f"{staff_count} 人")
            with c2:
                st.metric("所需羽球", f"{tubes_needed} 桶")
                st.metric("租借時數", f"{rent_hours} 小時")
            with c3:
                st.metric("總預算", f"${total_cost:,.0f}")
                if total_players > 0:
                    per_person = math.ceil(total_cost / total_players / 10) * 10
                    st.metric("建議每人報名費", f"${per_person}")

            st.markdown("### 費用明細")
            cost_data = [
                {"項目": "場地費", "計算式": f"{num_courts}面 * {rent_hours}hr * ${court_price_per_hr}", "金額": int(cost_court)},
                {"項目": "比賽用球", "計算式": f"{tubes_needed}桶 * ${shuttle_tube_price}", "金額": int(cost_shuttles)},
                {"項目": "獎牌/獎品", "計算式": f"{total_players}人 * ${medal_price}", "金額": int(cost_medals)},
                {"項目": "聚餐(熱炒)", "計算式": f"{total_players}人 * ${food_price}", "金額": int(cost_food)},
                {"項目": "工作人員", "計算式": f"{staff_count}人 * ${staff_fee}", "金額": int(cost_staff)},
            ]
            df_cost = pd.DataFrame(cost_data)
            df_cost["金額"] = df_cost["金額"].apply(lambda x: f"${x:,.0f}")
            st.table(df_cost)