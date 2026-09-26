import os
import subprocess
import pandas as pd

# ==========================================
# 1. 設定項目
# ==========================================
THRESHOLD = 0.95 # p < 0.05
SKELETON_MASK = "mean_FA_skeleton_mask.nii.gz"
FSLDIR = os.environ.get('FSLDIR', '/usr/local/fsl')

# 新しい出力先ディレクトリの作成
OUT_DIR = "TBSS_Tract_Results"
os.makedirs(OUT_DIR, exist_ok=True)

# JHU-tracts.xml に対応する画像（20領域の確率マップを二値化したアトラス）
ATLAS_FILE = f"{FSLDIR}/data/atlases/JHU/JHU-ICBM-tracts-maxprob-thr25-1mm.nii.gz"

# 読み込むファイル名（プレフィックス）の設定
file_names = {
    'FA': {'pval': 'tbss_tfce_corrp_tstat1.nii.gz', 'tstat': 'tbss_tstat1.nii.gz'},
    'MD': {'pval': 'tbss_MD_tfce_corrp_tstat1.nii.gz', 'tstat': 'tbss_MD_tstat1.nii.gz'},
    'AD': {'pval': 'tbss_AD_tfce_corrp_tstat1.nii.gz', 'tstat': 'tbss_AD_tstat1.nii.gz'},
    'RD': {'pval': 'tbss_RD_tfce_corrp_tstat1.nii.gz', 'tstat': 'tbss_RD_tstat1.nii.gz'}
}

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, text=True)
    return result.stdout.strip()

# ==========================================
# 2. トラクト名の動的抽出 (JHU-tracts.xml)
# ==========================================
print("--- Extracting Tract Labels ---")
txt_path = os.path.join(OUT_DIR, "labels_tracts.txt")
# ご提示のコマンドを実行（atlass -> atlases に修正済）
extract_cmd = f'cat {FSLDIR}/data/atlases/JHU-tracts.xml | grep label | cut -d ">" -f 2 | cut -d "<" -f 1 > {txt_path}'
run_cmd(extract_cmd)

# 抽出したテキストファイルを読み込み、辞書を作成
jhu_labels = {}
with open(txt_path, "r") as f:
    # XMLのindexは0から始まりますが、画像(NIfTI)の画素値は1から始まるため、start=1で対応させます
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
        # 一時ファイルも全て出力先ディレクトリ内に作成
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
            lines = cluster_out.split('\n')[1:] # 1行目のヘッダーを飛ばす
            
            best_t = -1
            best_coords = ""
            
            for line in lines:
                if not line.strip(): continue
                parts = line.split()
                t_val = float(parts[2])
                if t_val > best_t:
                    best_t = t_val
                    best_coords = f"{parts[3]}, {parts[4]}, {parts[5]}"

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
        # 割合（指標B）が高い順に並び替え
        df = df.sort_values(by='Percentage of Tract Affected (%)', ascending=False).reset_index(drop=True)
        
        csv_filename = os.path.join(OUT_DIR, f"TBSS_Results_Table_{metric}.csv")
        df.to_csv(csv_filename, index=False)
        print(f"-> Successfully saved: {csv_filename}")
    else:
        print(f"No tracts matched the significant voxels for {metric}.")
    print()

print("All processing complete. Outputs are located in the 'TBSS_Tract_Results' directory.")
