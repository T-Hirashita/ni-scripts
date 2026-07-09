#!/bin/bash

# BIDSディレクトリ内の "sub-" から始まるフォルダ名を取得してループ
for sub_dir in ./rawdata/sub-*; do
  # フォルダ名から "sub-" プレフィックスを取り除いてIDだけにする (例: sub-01 -> 01)
  sub_id=$(basename "$sub_dir" | sed 's/sub-//')
  
  echo "被験者 ${sub_id} の処理を開始します..."
  
  fmriprep-docker ./rawdata ./output participant \
    --participant-label "${sub_id}" \
    --fs-license-file /home/brain/freesurfer/7.4.0/license.txt \
    --work-dir ./wd
    
  echo "被験者 ${sub_id} の処理が終了しました。"
done
