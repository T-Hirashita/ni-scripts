#!/bin/bash
# ==============================================================================
# Script Name:  format_halfpipe_for_spm.sh
# Description:  Formats HALFpipe output for SPM12 analysis.
#               (To be executed inside the "derivatives" directory)
#               * Validates the existence of both "fmriprep" and "halfpipe".
#               * Merges extracted .nii and motion.txt into a new "spm_prep" dir.
#               * Original directories are kept STRICTLY UNTOUCHED.
# ==============================================================================

echo "=================================================================="
echo " HALFpipe -> SPM12 データ成型パイプライン (複数フォルダ統合版)"
echo "=================================================================="

# ------------------------------------------------------------------------------
# 1. ディレクトリの指定と確認
# ------------------------------------------------------------------------------
TARGET_DIR=$(pwd)
OUTPUT_DIR="./spm_prep"

echo "現在の作業ディレクトリ: $TARGET_DIR"

# 「fmriprep」「halfpipe」両方のフォルダが存在するか確認
if [ ! -d "./fmriprep" ] || [ ! -d "./halfpipe" ]; then
    echo "[エラー] このディレクトリ内に 'fmriprep' または 'halfpipe' フォルダが見つかりません。"
    echo "        必ず「/\"プロジェクト名\"/halfpipe-\"バージョン名\"/wd/derivatives」"
    echo "        に移動した状態でスクリプトを実行してください。"
    echo "        スクリプトを中断します。"
    exit 1
fi

echo "[確認] 'fmriprep' および 'halfpipe' フォルダを検出しました。"
echo "[準備] 統合出力先フォルダ '$OUTPUT_DIR' を作成します..."
mkdir -p "$OUTPUT_DIR"


# ------------------------------------------------------------------------------
# 2. サブジェクトごとのファイルの中身をnii.gz → niiに展開
# ------------------------------------------------------------------------------
echo -e "\n------------------------------------------------------------"
echo "[処理2-A] fmriprep フォルダから構造・機能画像を展開します..."
echo "------------------------------------------------------------"

find ./fmriprep -type f -name "*.nii.gz" | grep -E '/(anat|func)/' | while read -r gz_file; do
    # 相対パスを計算して、spm_prep内に同じ階層構造を作成
    rel_path="${gz_file#./fmriprep/}"                 # 例: sub-01/ses-1/anat/xxx.nii.gz
    out_dir_path="$OUTPUT_DIR/$(dirname "$rel_path")" # 例: ./spm_prep/sub-01/ses-1/anat
    
    mkdir -p "$out_dir_path"
    out_nii_file="$out_dir_path/$(basename "$gz_file" .gz)"
    
    if [ -f "$out_nii_file" ]; then
        echo "スキップ: $(basename "$out_nii_file")"
    else
        echo "展開中(fmriprep) : $(basename "$gz_file")"
        gunzip -c "$gz_file" > "$out_nii_file"
    fi
done


echo -e "\n------------------------------------------------------------"
echo "[処理2-B] halfpipe フォルダから機能画像を展開します..."
echo "------------------------------------------------------------"

# target: *_setting-preproc_bold.nii.gz
find ./halfpipe -type f -name "*setting-preproc_bold.nii.gz" | grep '/func/' | while read -r gz_file; do
    # 相対パスを計算して、spm_prep内の同じ被験者・セッションフォルダにマージ
    rel_path="${gz_file#./halfpipe/}"
    out_dir_path="$OUTPUT_DIR/$(dirname "$rel_path")"
    
    mkdir -p "$out_dir_path"
    out_nii_file="$out_dir_path/$(basename "$gz_file" .gz)"
    
    if [ -f "$out_nii_file" ]; then
        echo "スキップ: $(basename "$out_nii_file")"
    else
        echo "展開中(halfpipe) : $(basename "$gz_file")"
        gunzip -c "$gz_file" > "$out_nii_file"
    fi
done


# ------------------------------------------------------------------------------
# 3. desc-confounds_timeseries.tsv から6軸モーションの抽出
# ------------------------------------------------------------------------------
echo -e "\n------------------------------------------------------------"
echo "[処理3] fmriprep フォルダから頭部動揺パラメータを抽出します..."
echo "------------------------------------------------------------"

find ./fmriprep -type f -name "*_desc-confounds_timeseries.tsv" | grep '/func/' | while read -r tsv_file; do
    rel_path="${tsv_file#./fmriprep/}"
    out_dir_path="$OUTPUT_DIR/$(dirname "$rel_path")"
    
    mkdir -p "$out_dir_path"
    out_motion_file="$out_dir_path/motion.txt"
    
    # awkを使用して抽出 (ダミースキャン2行分を自動スキップ)
    awk -F'\t' -v drop=2 '
    NR==1 {
        for(i=1; i<=NF; i++) {
            if($i=="trans_x") c[1]=i
            if($i=="trans_y") c[2]=i
            if($i=="trans_z") c[3]=i
            if($i=="rot_x")   c[4]=i
            if($i=="rot_y")   c[5]=i
            if($i=="rot_z")   c[6]=i
        }
        next
    }
    NR <= (1 + drop) {
        # ヘッダー(1行目) + ダミースキャン(drop数) までの行は読み飛ばす
        next
    }
    {
        print $c[1], $c[2], $c[3], $c[4], $c[5], $c[6]
    }' "$tsv_file" > "$out_motion_file"
    
    if [ $? -eq 0 ]; then
        echo "抽出成功: $(basename "$tsv_file") -> motion.txt"
    else
        echo "[警告] $(basename "$tsv_file") の処理中にエラーが発生しました。"
        rm -f "$out_motion_file"
    fi
done

echo -e "\n=================================================================="
echo " すべての処理が完了しました。"
echo " 構造画像・機能画像・motion.txt が '$OUTPUT_DIR' フォルダ内に"
echo " 綺麗にマージされて保存されています。"
echo "=================================================================="