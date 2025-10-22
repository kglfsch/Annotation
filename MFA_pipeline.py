import os
import sys
import shutil
import subprocess
import pandas as pd
from praatio import textgrid

# STEP 1: preprocess the ASR output (.csv to .txt)
def csv_to_txt(csv_path, txt_path):
    df = pd.read_csv(csv_path, sep=";")

    # get words in the 'ORT' column
    words = df["ORT"].dropna().astype(str).tolist()
    with open(txt_path, "w", encoding="utf-8") as f:
        for word in words:
            f.write(word.strip() + "\n")
    
    print(f"Converted {len(words)} phrasal words.")

# STEP 2: create folder & move .wav and .txt files
def organize_files(base_dir, file_id, mode="to_subfolder"):
    folder_path = os.path.join(base_dir, f"p{file_id}")
    os.makedirs(folder_path, exist_ok=True)
    
    for typ in ["wav", "txt"]:
        # set the source and destination path depending on the mode
        src, dst = (
            (os.path.join(base_dir, f"{file_id}.{typ}"), os.path.join(folder_path, f"{file_id}.{typ}"))
            if mode == "to_subfolder"
            else (os.path.join(folder_path, f"{file_id}.{typ}"), os.path.join(base_dir, f"{file_id}.{typ}"))
        )
        

        try:
            shutil.move(src, dst)
            if os.path.exists(src):
                print(f"Move failed: {src} still exists")
            else:
                print(f"Move successful: {dst}")
        except Exception as e:
            print(f"Error during move: {e}")

# STEP 3: run MFA (option: "--single_speaker", "--clean")
def run_mfa(staging_dir, dict_path, model_path, output_dir):
    print("Running MFA alignment on all files...")
    subprocess.run([
        "mfa", "align", "--clean", "--single_speaker",
        staging_dir, dict_path, model_path, output_dir, 
    ])
    print("MFA alignment complete.")

# STEP 4: merge intervals in the mfa .TextGrid file output
def from_pauses(textgrid_path, output_path, pause_threshold=0.2):
    tg = textgrid.openTextgrid(textgrid_path, includeEmptyIntervals=True)
    if "words" not in tg.tierNames:
        raise ValueError("No 'words' tier found in TextGrid")
    word_tier = tg.getTier("words")
    entries = word_tier.entries

    sentence_intervals = []
    sentence = []
    sentence_start = None

    for i, (start, end, label) in enumerate(entries):
        label = label.strip()
        if label != "":
            if sentence_start is None:
                sentence_start = start
            sentence.append((start, end, label))
            if i + 1 < len(entries):
                next_label = entries[i + 1][2].strip()
                if next_label == "":
                    sentence_end = end
                    sentence_intervals.append((sentence_start, sentence_end, sentence))
                    sentence = []
                    sentence_start = None
        elif sentence:
            sentence_end = entries[i - 1][1]
            sentence_intervals.append((sentence_start, sentence_end, sentence))
            sentence = []
            sentence_start = None

    new_entries = []
    for start, end, word_list in sentence_intervals:
        combined = "".join([w for _, _, w in word_list])
        new_entries.append((start, end, combined))

    for tier in ["phones", "words"]:
        if tier in tg.tierNames:
            tg.removeTier(tier)

    tg.addTier(textgrid.IntervalTier(name="turns", entries=[], minT=0, maxT=tg.maxTimestamp))
    tg.addTier(textgrid.IntervalTier(name="utterances", entries=new_entries, minT=0, maxT=tg.maxTimestamp))
    tg.addTier(textgrid.IntervalTier(name="FPs", entries=[], minT=0, maxT=tg.maxTimestamp))

    tg.save(output_path, format="short_textgrid", includeBlankSpaces=True)
    print(f"Saved merged TextGrid to {output_path}")

# MAIN PIPELINE
def main():
    if len(sys.argv) != 2:
        print("Usage: python preprocessing_annotation_folder.py <base_dir>")
        return

    base_dir = sys.argv[1]
    files = os.listdir(base_dir)

    # Step 0: find all file pairs of .csv and .wav
    base_ids = set(f.split('.')[0] for f in files if f.endswith(".csv"))
    matched_ids = [fid for fid in base_ids if f"{fid}.wav" in files]
    print(f"Found {len(matched_ids)} valid file pairs.")

    # Step 1: csv to txt
    for file_id in matched_ids:
        try:
            print(f"\n[Step 1] Converting {file_id}.csv → .txt")
            csv_path = os.path.join(base_dir, f"{file_id}.csv")
            txt_path = os.path.join(base_dir, f"{file_id}.txt")
            csv_to_txt(csv_path, txt_path)
        except Exception as e:
            print(f"Error converting {file_id}: {e}")

    # Step 2: organize files
    for file_id in matched_ids:
        try:
            print(f"\n[Step 2] Organizing {file_id}")
            organize_files(base_dir, file_id, mode="to_subfolder")
        except Exception as e:
            print(f"Error organizing {file_id}: {e}")

    # Step 3: run MFA
    try:
        print(f"\n[Step 3] Running MFA on {base_dir}")
        aligned_dir = os.path.join(base_dir, "aligned")
        run_mfa(base_dir, "korean_mfa", "korean_mfa", aligned_dir)
    except Exception as e:
        print(f"MFA failed: {e}")
        return

    # Step 4: merge intervals in TextGrid created by MFA
    for file_id in matched_ids:
        try:
            print(f"\n[Step 4] Merging intervals for {file_id}")
            aligned_textgrid_path = os.path.join(aligned_dir, f"p{file_id}", f"{file_id}.TextGrid")
            output_path = os.path.join(base_dir, f"{file_id}_preprocessed.TextGrid")
            from_pauses(aligned_textgrid_path, output_path)
        except Exception as e:
            print(f"Error merging intervals of {file_id}: {e}")
    
    # Step 5: move .wav files back to base
    for file_id in matched_ids:
        try:
            print(f"\n[Step 5] Moving {file_id}.wav back to base")
            organize_files(base_dir, file_id, mode="to_base")
        except Exception as e:
            print(f"Error moving {file_id}.wav: {e}")


if __name__ == "__main__":
    main()
