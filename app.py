import streamlit as st
import pandas as pd
import numpy as np
import math
import random
import json
import io
from datetime import datetime, timedelta, time
import graphviz # 用於畫樹狀圖

# 設定頁面寬度
st.set_page_config(layout="wide", page_title="熊德盃賽事規劃系統 v4.0 (旗艦版)")

# --- CSS 優化 ---
st.markdown("""
<style>
    .stDataFrame {font-size: 1.1rem;}
    div[data-testid="stMetricValue"] {font-size: 1.8rem;}
    /* 讓表格標題置中 */
    th {text-align: center !important;}
    td {text-align: center !important;}
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
    st.session_state.schedule_list = [] # 儲存排序後的比賽清單供樹狀圖使用

# --- 顏色定義 (用於賽程大表) ---
# 定義一組好看的顏色 (淺色底，深色字)
COLOR_PALETTE = {
    0: '#FFCDD2', # 紅
    1: '#C8E6C9', # 綠
    2: '#BBDEFB', # 藍
    3: '#FFF9C4', # 黃
    4: '#E1BEE7', # 紫
    5: '#FFE0B2', # 橘
    6: '#B2DFDB', # 青
    7: '#F0F4C3', # 萊姆
}

def get_group_color(level_name, all_levels):
    """根據組別名稱回傳 HEX 顏色碼"""
    try:
        idx = all_levels.index(level_name) % len(COLOR_PALETTE)
        return COLOR_PALETTE[idx]
    except:
        return '#FFFFFF' # 預設白

# --- 側邊欄：全域設定 ---
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
    st.info(f"ℹ️ 一場對戰佔用: {total_matchup_duration} 分鐘")

if not is_guest_mode:
    with st.sidebar.expander("2. 費用與資源估算"):
        shuttles_per_point = st.number_input("每點(每局)使用球數", 1, 6, 2)
        shuttle_tube_price = st.number_input("每桶球價格 ($)", 0, 2000, 950)
        court_price_per_hr = st.number_input("場地費/面/時 ($)", 0, 2000, 500)
        medal_price = st.number_input("獎牌費/人 ($)", 0, 1000, 200)
        food_price = st.number_input("熱炒費/人 ($)", 0, 2000, 500)
        players_per_team = st.number_input("每隊人數", 1, 20, 6)
        
        st.markdown("---")
        # 新增工作人員欄位
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
st.title("🏸 熊德盃羽球比賽 賽制規劃/查詢系統 v4.0")

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
                # 勝部
                match_sf1 = {"type": "複賽-勝部", "level": "決賽區", "team_a": f"{group_1} 冠軍", "team_b": f"{group_2} 亞軍", "desc": "4強賽 A1vsB2"}
                match_sf2 = {"type": "複賽-勝部", "level": "決賽區", "team_a": f"{group_2} 冠軍", "team_b": f"{group_1} 亞軍", "desc": "4強賽 B1vsA2"}
                st.session_state.matches.extend([match_sf1, match_sf2])
                
                # 敗部
                if include_loser:
                    match_ls1 = {"type": "複賽-敗部", "level": "敗部區", "team_a": f"{group_1} 季軍", "team_b": f"{group_2} 殿軍", "desc": "敗部4強 A3vsB4"}
                    match_ls2 = {"type": "複賽-敗部", "level": "敗部區", "team_a": f"{group_2} 季軍", "team_b": f"{group_1} 殿軍", "desc": "敗部4強 B3vsA4"}
                    match_l_final = {"type": "決賽-敗部", "level": "敗部區", "team_a": "敗部4強 勝方1", "team_b": "敗部4強 勝方2", "desc": "🛡️ 敗部冠軍賽"}
                    st.session_state.matches.extend([match_ls1, match_ls2, match_l_final])
                
                # 決賽
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
    
    st.markdown(f"**說明**：不同底色代表不同分組，數字為唯一場次編號 (Match No.)")
    
    if not is_guest_mode:
        if st.button("🚀 開始排程 (生成大表)"):
            if not st.session_state.matches:
                st.error("無賽程資料")
            else:
                sort_matches_by_priority()
                
                # 準備 Grid 和 顏色 Grid
                schedule_grid = [["" for _ in range(num_courts)] for _ in range(slots_count)]
                color_grid = [["#FFFFFF" for _ in range(num_courts)] for _ in range(slots_count)]
                
                match_queue = st.session_state.matches.copy()
                team_busy_until = {} 
                
                # 取得所有組別以便配色
                all_levels = sorted(list(set(m['level'] for m in st.session_state.matches)))
                
                scheduled_matches_list = [] # 儲存排好的比賽，含 Match No.
                global_match_counter = 1    # 全域場次編號

                # 開始填格子 (由左至右，由上至下)
                for row in range(slots_count):
                    if row + points_per_matchup > slots_count: break
                    
                    # 每一列重新排序 Queue (確保優先級)
                    if match_queue:
                         match_queue.sort(key=get_match_priority)

                    for col in range(num_courts):
                        if not match_queue: break
                        if schedule_grid[row][col] != "": continue
                            
                        found_match_idx = -1
                        
                        # 搜尋邏輯
                        for idx, match in enumerate(match_queue):
                            ta, tb = match['team_a'], match['team_b']
                            
                            # 嚴格階段鎖定: 如果佇列中有更優先的比賽，就不能排這場
                            min_p = min(get_match_priority(m) for m in match_queue)
                            if get_match_priority(match) > min_p:
                                continue
                            
                            # 物理限制
                            is_ta_busy = row < team_busy_until.get(ta, -1)
                            is_tb_busy = row < team_busy_until.get(tb, -1)
                            
                            if not is_ta_busy and not is_tb_busy:
                                found_match_idx = idx
                                break
                        
                        if found_match_idx != -1:
                            match = match_queue.pop(found_match_idx)
                            current_match_no = global_match_counter
                            global_match_counter += 1
                            
                            end_row = row + points_per_matchup
                            
                            # 內容文字
                            desc_text = match['desc']
                            info_text = f"No.{current_match_no}\n{match['team_a']}\nvs\n{match['team_b']}\n({match['level']})"
                            
                            # 顏色
                            bg_color = get_group_color(match['level'], all_levels)
                            if "決賽" in match['type']: bg_color = "#FFCDD2" # 決賽區紅色
                            if "敗部" in match['type']: bg_color = "#E1BEE7" # 敗部區紫色
                            
                            schedule_grid[row][col] = info_text
                            color_grid[row][col] = f"background-color: {bg_color}"
                            
                            for r in range(row + 1, end_row):
                                schedule_grid[r][col] = f"No.{current_match_no} ..."
                                color_grid[r][col] = f"background-color: {bg_color}; color: #666"
                            
                            team_busy_until[match['team_a']] = end_row
                            team_busy_until[match['team_b']] = end_row
                            
                            # 存入列表供後續使用
                            match['match_no'] = current_match_no
                            match['time'] = (play_start + timedelta(minutes=row*mins_per_point)).strftime("%H:%M")
                            scheduled_matches_list.append(match)

                # 儲存結果
                time_labels = []
                for i in range(slots_count):
                    t = play_start + timedelta(minutes=i*mins_per_point)
                    time_labels.append(t.strftime("%H:%M"))
                    
                col_labels = [f"Court {i+1}" for i in range(num_courts)]
                
                st.session_state.schedule = pd.DataFrame(schedule_grid, index=time_labels, columns=col_labels)
                st.session_state.schedule_color = pd.DataFrame(color_grid, index=time_labels, columns=col_labels)
                st.session_state.schedule_list = scheduled_matches_list # 存下帶有 No. 的列表
                
                if match_queue:
                    st.warning(f"⚠️ 尚有 {len(match_queue)} 場排不進去")
                else:
                    st.success("✅ 賽程大表生成完畢！")

    # 顯示賽程大表
    if st.session_state.schedule is not None:
        st.divider()
        
        # 圖例
        st.write("🎨 **組別色碼圖例**：")
        cols = st.columns(8)
        all_levels = sorted(list(set(m['level'] for m in st.session_state.matches)))
        for i, level in enumerate(all_levels):
            c = get_group_color(level, all_levels)
            cols[i % 8].markdown(f"<div style='background-color:{c};padding:5px;border-radius:5px;text-align:center'>{level}</div>", unsafe_allow_html=True)
        
        st.write("")
        
        # 使用 Styler 上色
        def style_apply(df):
            return st.session_state.schedule_color

        st.dataframe(
            st.session_state.schedule.style.apply(lambda x: st.session_state.schedule_color, axis=None),
            height=800,
            use_container_width=True
        )
        
        # 下載 Excel 按鈕
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            st.session_state.schedule.to_excel(writer, sheet_name='賽程大表')
            # 另外存一個清單
            df_list = pd.DataFrame(st.session_state.schedule_list)
            if not df_list.empty:
                df_list = df_list[['match_no', 'time', 'level', 'team_a', 'team_b', 'desc']]
                df_list.to_excel(writer, sheet_name='對戰清單')
        
        st.download_button(
            label="📥 一鍵下載 Excel (可貼到 Google Sheets)",
            data=buffer.getvalue(),
            file_name="badminton_master_schedule.xlsx",
            mime="application/vnd.ms-excel"
        )

# ==========================================
# Tab 4: 樹狀圖與名次 (新功能)
# ==========================================
tree_tab_idx = 1 if is_guest_mode else 3
with tabs[tree_tab_idx]:
    st.subheader("🏆 晉級樹狀圖 (Brackets)")
    
    if not st.session_state.schedule_list:
        st.info("請先在「排程」頁面完成排程，才能生成帶有場次編號的樹狀圖。")
    else:
        # 準備資料
        matches = st.session_state.schedule_list
        
        # 分離勝部與敗部
        winner_bracket = [m for m in matches if "勝部" in m['type'] or "決賽" in m['type']]
        loser_bracket = [m for m in matches if "敗部" in m['type']]
        
        # 繪製勝部
        st.markdown("### 🥇 勝部 / 總決賽樹狀圖")
        graph = graphviz.Digraph()
        graph.attr(rankdir='LR') # 左到右
        
        for m in winner_bracket:
            label = f"Match {m['match_no']}\n{m['desc']}\n({m['team_a']} vs {m['team_b']})"
            graph.node(str(m['match_no']), label, shape='box', style='filled', fillcolor='#FFEB3B')
            
            # 這裡簡單模擬連接，實際樹狀圖邏輯需要更複雜的 id 追蹤
            # 這裡我們用文字列表呈現供複製
        
        # 由於 Graphviz 在 Streamlit 有時顯示較小，我們提供一個「填分表格」
        st.info("👇 下方表格可直接複製到 Google Sheets 作為樹狀圖填分使用")
        
        # 製作 Excel 友善的表格
        bracket_data = []
        for m in winner_bracket:
            bracket_data.append({
                "Match No.": m['match_no'],
                "Stage": m['desc'],
                "Team A": m['team_a'],
                "Score A": "",
                "Score B": "",
                "Team B": m['team_b']
            })
        
        df_winner = pd.DataFrame(bracket_data)
        st.dataframe(df_winner, use_container_width=True)
        
        # 敗部
        if loser_bracket:
            st.divider()
            st.markdown("### 🛡️ 敗部復活樹狀圖")
            loser_data = []
            for m in loser_bracket:
                loser_data.append({
                    "Match No.": m['match_no'],
                    "Stage": m['desc'],
                    "Team A": m['team_a'],
                    "Score A": "",
                    "Score B": "",
                    "Team B": m['team_b']
                })
            df_loser = pd.DataFrame(loser_data)
            st.dataframe(df_loser, use_container_width=True)

        # 匯出樹狀圖表格
        buffer_bracket = io.BytesIO()
        with pd.ExcelWriter(buffer_bracket, engine='openpyxl') as writer:
            df_winner.to_excel(writer, sheet_name='勝部樹狀圖表格', index=False)
            if loser_bracket:
                df_loser.to_excel(writer, sheet_name='敗部樹狀圖表格', index=False)
                
        st.download_button(
            label="📥 下載樹狀圖填分表 (Excel)",
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
            cost_staff = staff_count * staff_fee # 新增
            
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
                {"項目": "工作人員", "計算式": f"{staff_count}人 * ${staff_fee}", "金額": int(cost_staff)}, # 新增
            ]
            df_cost = pd.DataFrame(cost_data)
            df_cost["金額"] = df_cost["金額"].apply(lambda x: f"${x:,.0f}")
            st.table(df_cost)