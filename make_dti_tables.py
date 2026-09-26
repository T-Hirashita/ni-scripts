import os
import subprocess
import pandas as pd

# ==========================================
# 1. 設定項目
# ==========================================
# ワーキングディレクトリの指定と移動
WORK_DIR = "../dwi/dti/TBSS58/stats/"
os.chdir(WORK_DIR)

THRESHOLD = 0.95 # p < 0.05
SKELETON_MASK = "mean_FA_skeleton_mask.nii.gz"
FSLDIR = os.environ.get('FSLDIR', '/usr/local/fsl')

# 新しい出力先ディレクトリの作成（statsディレクトリ内に作成されます）
OUT_DIR = "TBSS_Tract_Results"
os.makedirs(OUT_DIR, exist_ok=True)

# JHU-tracts.xml に対応する画像（20領域の確率マップを二値化したアトラス）
ATLAS_FILE = f"{FSLDIR}/data/atlases/JHU/JHU-ICBM-tracts-maxprob-thr25-1mm.nii.gz"

# 読み込むファイル名（プレフィックス）の設定
file_names = {
    'FA': {'pval': 'tbssFA_tfce_corrp_tstat1.nii.gz', 'tstat': 'tbssFA_tstat1.nii.gz'},
    'MD': {'pval': 'tbssMD_tfce_corrp_tstat1.nii.gz', 'tstat': 'tbssMD_tstat1.nii.gz'},
    'AD': {'pval': 'tbssL1_tfce_corrp_tstat1.nii.gz', 'tstat': 'tbssL1_tstat1.nii.gz'},
    'RD': {'pval': 'tbssRD_tfce_corrp_tstat1.nii.gz', 'tstat': 'tbssRD_tstat1.nii.gz'}
}

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, text=True)
    return result.stdout.strip()

# ==========================================
# 2. トラクト名の動的抽出 (JHU-tracts.xml)
# ==========================================
print(f"Working Directory: {os.getcwd()}")
print("--- Extracting Tract Labels ---")
txt_path = os.path.join(OUT_DIR, "labels_tracts.txt")
extract_cmd = f'cat {FSLDIR}/data/atlases/JHU-tracts.xml | grep label | cut -d ">" -f 2 | cut -d "<" -f 1 > {txt_path}'
run_cmd(extract_cmd)

# 抽出したテキストファイルを読み込み、辞書を作成
jhu_labels = {}
with open(txt_path, "r") as f:
    for idx, line in enumerate(f, start=1):
        name = line.strip()
        if name:
            jhu_labels[idx] = name

print(f"-> Extracted {len(jhu_labels)} tracts and saved to {txt_path}\n")

# ==========================================
# 3. メインの処理ループ
# ==========================================
for metric, files in file_names.items():
    pval_file = files['pval']
    tstat_file = files['tstat']

    if not os.path.exists(pval_file):
        print(f"Skipping {metric}: File {pval_file} not found.")
        continue

    print(f"--- Processing {metric} ---")
    sig_mask = os.path.join(OUT_DIR, f"temp_sig_{metric}.nii.gz")
    run_cmd(f"fslmaths {pval_file} -thr {THRESHOLD} -bin {sig_mask}")
    
    # 有意ボクセルが1つも無い場合はスキップ
    if run_cmd(f"fslstats {sig_mask} -V").split()[0] == "0":
        print(f"No significant results for {metric}.\n")
        os.remove(sig_mask)
        continue

    results = []

    for idx, tract_name in jhu_labels.items():
        tract_raw = os.path.join(OUT_DIR, f"temp_raw_{idx}.nii.gz")
        tract_skel = os.path.join(OUT_DIR, f"temp_skel_{idx}.nii.gz")
        tract_sig = os.path.join(OUT_DIR, f"temp_sig_tract_{idx}.nii.gz")

        # A. アトラスからトラクトを抽出し、白質スケルトンと掛け合わせる
        run_cmd(f"fslmaths {ATLAS_FILE} -thr {idx} -uthr {idx} -bin {tract_raw}")
        run_cmd(f"fslmaths {tract_raw} -mul {SKELETON_MASK} {tract_skel}")
        
        # そのトラクト本来の白質スケルトンの総ボクセル数を取得
        total_voxels_str = run_cmd(f"fslstats {tract_skel} -V")
        if not total_voxels_str or total_voxels_str.split()[0] == "0":
            for f in [tract_raw, tract_skel]: os.remove(f) if os.path.exists(f) else None
            continue
        total_voxels = float(total_voxels_str.split()[0])

        # B. さらに有意領域マスクと掛け合わせる
        run_cmd(f"fslmaths {tract_skel} -mul {sig_mask} {tract_sig}")
        sig_voxels = float(run_cmd(f"fslstats {tract_sig} -V").split()[0])

        # C. そのトラクト内に有意差があれば、割合とピーク座標を計算
        if sig_voxels > 0:
            percentage = (sig_voxels / total_voxels) * 100
            
            # clusterコマンドを利用してMNI座標と最大t値を抽出
            cluster_out = run_cmd(f"cluster -i {tract_sig} -t 0.5 --cope={tstat_file} --mm")
            lines = cluster_out.split('\n')[1:] 
            
            best_t = -1
            best_coords = ""
            
            for line in lines:
                if not line.strip(): continue
                parts = line.split()
                # 修正ポイント: 
                # --copeオプション使用時の列の構成に対応
                # parts[2] は入力画像の最大値(1)、parts[9]がCOPE(t値)の最大値、10〜12がそのMNI座標です。
                if len(parts) >= 13:
                    t_val = float(parts[9])
                    if t_val > best_t:
                        best_t = t_val
                        best_coords = f"{parts[10]}, {parts[11]}, {parts[12]}"

            results.append({
                'Anatomical Tract': tract_name,
                'Significant Voxels': int(sig_voxels),
                'Percentage of Tract Affected (%)': round(percentage, 1),
                'Peak t-value': round(best_t, 2),
                'Peak MNI Coordinate (x, y, z)': best_coords
            })

        # 一時ファイルの削除
        for f in [tract_raw, tract_skel, tract_sig]:
            if os.path.exists(f): os.remove(f)
            
    if os.path.exists(sig_mask): os.remove(sig_mask)

    # データを整形してCSVに出力
    if results:
        df = pd.DataFrame(results)
        df = df.sort_values(by='Percentage of Tract Affected (%)', ascending=False).reset_index(drop=True)
        
        csv_filename = os.path.join(OUT_DIR, f"TBSS_Results_Table_{metric}.csv")
        df.to_csv(csv_filename, index=False)
        print(f"-> Successfully saved: {csv_filename}")
    else:
        print(f"No tracts matched the significant voxels for {metric}.")
    print()

print("All processing complete. Outputs are located in the 'TBSS_Tract_Results' directory.")
