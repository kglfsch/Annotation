import os
import sys
import glob
import pandas as pd
from praatio import textgrid

# STEP 1: Add 'condition' tier to the TextGrid with response condition labels
def get_list_num(participant_id, condition_df):
    # get the list for each participant
    for col in condition_df.columns:
        id_in_col = str(condition_df[col].iloc[1]).zfill(2)  # index 1!
        if id_in_col == str(participant_id).zfill(2):
            return col
    raise ValueError(f"No list number found for participant ID: {participant_id}")

def add_condition_tier(tg, list_num, condition_df):
    new_entries = []

    turns_tier = tg.getTier("turns")
    entries = turns_tier.entries

    for entry in entries:
        label = entry[2]
        if label.startswith("R"):
            # extract the question number (e.g., R010 -> 1) and then adjust for index by adding 1 (because the first row is participant ID)
            rownum = int(label[1:3]) + 1
            condition = condition_df[list_num].iloc[rownum]  # Look up the condition (T or D)
            new_entries.append((entry[0], entry[1], condition))

    tg.addTier(textgrid.IntervalTier(name="condition", entries=new_entries, minT=0, maxT=tg.maxTimestamp))
    return tg


# STEP 2: Extract numerical data from TextGrid files
# Extract response latency (RL)
def extract_rl(tg, participant_id, list_num):
    results = []
    turns_tier = tg.getTier("turns")
    condition_tier = tg.getTier("condition")

    entries = turns_tier.entries

    for i in range(0, len(entries) - 1, 2):
        q_entry = entries[i]
        r_entry = entries[i + 1]

        if not (q_entry[2].startswith("Q") and r_entry[2].startswith("R")):
            continue

        # RL in ms
        rl = round((r_entry[0] - q_entry[1]) * 1000, 3)
        question_num = q_entry[2][1:]
        
        # find the condition for this response based on start time
        cond = None
        for cond_entry in condition_tier.entries:
            if abs(cond_entry[0] - r_entry[0]) < 1e-6:
                cond = cond_entry[2]
                break
        
        if cond is None:
            raise ValueError(f"Condition not found for response {question_num} in participant {participant_id}, list {list_num}")

        results.append({
            "ParticipantID": participant_id,
            "ListNum": list_num,
            "QuestionNum": question_num,
            "ResponseCond": cond,
            "RLMilSec": rl
        })

    return results


# Extract speaking rate (SR)
def extract_sr(tg, participant_id, list_num):
    results = []
    turns_tier = tg.getTier("turns")
    utterances_tier = tg.getTier("utterances")
    condition_tier = tg.getTier("condition")

    entries = turns_tier.entries

    for i in range(0, len(entries)):
        entry = entries[i]
        if not entry[2].startswith("R"):
            continue

        # extract duration of the response in seconds
        response_start, response_end = entry[0], entry[1]
        duration = round(response_end - response_start, 3)

        # count characters in utterances within the response interval
        syllable_num = 0
        for utt in utterances_tier.entries:
            if utt[0] >= response_start and utt[1] <= response_end:
                syllable_num += len(utt[2])

        sr = round(syllable_num / duration, 3) if duration > 0 else 0
        question_num = entry[2][1:]

        # find the condition for this response based on start time
        cond = None
        for cond_entry in condition_tier.entries:
            if abs(cond_entry[0] - entry[0]) < 1e-6:
                cond = cond_entry[2]
                break
        
        if cond is None:
            raise ValueError(f"Condition not found for response {question_num} in participant {participant_id}, list {list_num}")

        results.append({
            "ParticipantID": participant_id,
            "ListNum": list_num,
            "QuestionNum": question_num,
            "ResponseCond": cond,
            "DurationSec": duration,
            "SyllNum": syllable_num,
            "SR": sr
        })

    return results


# Extract FP rate (FR): per condition, per item, per turn
def extract_fr(tg, participant_id, list_num):
    turns_tier = tg.getTier("turns")
    fps_tier = tg.getTier("FPs")
    condition_tier = tg.getTier("condition")

    # dictionaries to save different rates
    per_cond = {} # one rate per condition and question type
    per_item = {} # one rate per item
    per_turn = {} # one rate per turn

    entries = turns_tier.entries

    for i in range(0, len(entries)):
        entry = entries[i]
        if not entry[2].startswith("R"):
            continue

        response_start, response_end = entry[0], entry[1]
        response_label = entry[2]

        # save item and turn IDs
        item_id = response_label[1:3]  # e.g., R010 -> 01
        turn_id = response_label[1:]   # e.g., R010 -> 010

        # find question type
        question_type = None
        if response_label.endswith("0"):
            question_type = "Main"
        else:
            question_type = "FollowUp"

        # find matching condition
        cond = None
        for cond_entry in condition_tier.entries:
            if abs(cond_entry[0] - response_start) < 1e-6:
                cond = cond_entry[2]
                break

        if cond is None:
            raise ValueError(f"Condition not found for response {entry[2][1:]} in participant {participant_id}, list {list_num}")

        # count FPs within the response interval
        fp_count = 0
        for fp in fps_tier.entries:
            if fp[0] >= response_start and fp[1] <= response_end:
                fp_count += 1

        # calculate the duration of the response in seconds
        duration = round(response_end - response_start, 3)

        # update the dict: per condition and question type
        key = (cond, question_type)
        if key not in per_cond:
            per_cond[key] = {"FP": 0, "Duration": 0}

        per_cond[key]["FP"] += fp_count
        per_cond[key]["Duration"] += duration

        # update the dict: per item
        key_item = (item_id, cond)
        if key_item not in per_item:
            per_item[key_item] = {"FP": 0, "Duration": 0}
        per_item[key_item]["FP"] += fp_count
        per_item[key_item]["Duration"] += duration

        # update the dict: per turn
        per_turn[turn_id] = {"FP": fp_count, "Duration": duration, "Cond": cond, "QuestionType": question_type}

    # prepare results for output
    cond_results = []
    item_results = []
    turn_results = []

    # per condition results
    for (cond, question_type), vals in per_cond.items():
        total_duration_min = round(vals["Duration"] / 60, 3)
        fr = round(vals["FP"] / total_duration_min, 3) if total_duration_min > 0 else 0
        cond_results.append({
            "ParticipantID": participant_id,
            "ListNum": list_num,
            "ResponseCond": cond,
            "QuestionType": question_type,
            "SumDurationMin": total_duration_min,
            "Freq": vals["FP"],
            "FR": fr
        })

    # per item results
    for (item_id, cond), vals in per_item.items():
        total_duration_min = round(vals["Duration"] / 60, 3)
        fr = round(vals["FP"] / total_duration_min, 3) if total_duration_min > 0 else 0
        item_results.append({
            "ParticipantID": participant_id,
            "ListNum": list_num,
            "ItemID": item_id,
            "ResponseCond": cond,
            "SumDurationMin": total_duration_min,
            "Freq": vals["FP"],
            "FR": fr
        })
    
    # per turn results
    for turn_id, vals in per_turn.items():
        duration_min = round(vals["Duration"] / 60, 3)
        fr = round(vals["FP"] / duration_min, 3) if duration_min > 0 else 0
        turn_results.append({
            "ParticipantID": participant_id,
            "ListNum": list_num,
            "QuestionNum": turn_id,
            "ResponseCond": vals["Cond"],
            "QuestionType": vals["QuestionType"],
            "DurationMin": duration_min,
            "Freq": vals["FP"],
            "FR": fr
        })

    return cond_results, item_results, turn_results


# Extract FP forms and positions
def extract_fp_form_pos(tg, participant_id, list_num):
    turns_tier = tg.getTier("turns")
    fps_tier = tg.getTier("FPs")
    condition_tier = tg.getTier("condition")

    results = []
    entries = turns_tier.entries

    for i in range(0, len(entries)):
        entry = entries[i]
        if not entry[2].startswith("R"):
            continue

        response_start, response_end = entry[0], entry[1]
        question_num = entry[2][1:]

        # find matching condition
        cond = None
        for cond_entry in condition_tier.entries:
            if abs(cond_entry[0] - response_start) < 1e-6:
                cond = cond_entry[2]
                break

        if cond is None:
            raise ValueError(f"Condition not found for response {question_num} in participant {participant_id}, list {list_num}")


        # find FPs within the response interval and save their forms and positions (turn INItial or INTernal)
        for fp in fps_tier.entries:
            if fp[0] >= response_start and fp[1] <= response_end:
                form = fp[2]
                position = "INI" if fp[0] == response_start else "INT"

                results.append({
                    "ParticipantID": participant_id,
                    "ListNum": list_num,
                    "QuestionNum": question_num,
                    "ResponseCond": cond,
                    "Form": form,
                    "Position": position
                })

    return results


# MAIN PIPELINE
def process_files(textgrid_folder, condition_excel, output_folder):
    # load condition sheet
    condition_df = pd.read_excel(condition_excel, header=None)

    # find all TextGrid files in the input folder
    textgrid_paths = glob.glob(os.path.join(textgrid_folder, "*.TextGrid"))

    all_rl = []
    all_sr = []
    fr_cond = []
    fr_item = []
    fr_turn = []
    all_fp_pos = []

    # run through each TextGrid file
    for tg_path in textgrid_paths:
        filename = os.path.basename(tg_path)
        participant_id = filename.split("_")[0]  # e.g., 02 from "02_preprocessed.TextGrid"
        list_num = get_list_num(participant_id, condition_df)

        print(f"Processing: {filename}, {list_num}")

        tg = textgrid.openTextgrid(tg_path, includeEmptyIntervals=False)

        tg = add_condition_tier(tg, list_num, condition_df)
        
        # save the modified TextGrid with the new condition tier
        new_tg_path = os.path.join(os.path.dirname(tg_path), f"{participant_id}_extracted.TextGrid")
        tg.save(new_tg_path, format="short_textgrid", includeBlankSpaces=True)

        all_rl.extend(extract_rl(tg, participant_id, list_num))
        all_sr.extend(extract_sr(tg, participant_id, list_num))
        fr_cond_res, fr_item_res, fr_turn_res = extract_fr(tg, participant_id, list_num)
        fr_cond.extend(fr_cond_res)
        fr_item.extend(fr_item_res)
        fr_turn.extend(fr_turn_res)
        all_fp_pos.extend(extract_fp_form_pos(tg, participant_id, list_num))

    # create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # save all results to CSV files
    pd.DataFrame(all_rl).to_csv(os.path.join(output_folder, "ResponseLatency.csv"), index=False)
    pd.DataFrame(all_sr).to_csv(os.path.join(output_folder, "SpeakingRate.csv"), index=False)
    pd.DataFrame(fr_cond).to_csv(os.path.join(output_folder, "FP_Rate_Condition.csv"), index=False)
    pd.DataFrame(fr_item).to_csv(os.path.join(output_folder, "FP_Rate_Item.csv"), index=False)
    pd.DataFrame(fr_turn).to_csv(os.path.join(output_folder, "FP_Rate_Turn.csv"), index=False)
    pd.DataFrame(all_fp_pos).to_csv(os.path.join(output_folder, "FP_Form_Position.csv"), index=False)

    print(f"RL: {len(all_rl)} rows")
    print(f"SR: {len(all_sr)} rows")
    print(f"FR: Per condition: {len(fr_cond)} rows, Per item: {len(fr_item)} rows, Per turn: {len(fr_turn)} rows")
    print(f"FP forms and positions: {len(all_fp_pos)} rows")
    print(f"Results saved to: {output_folder}")

# Example usage
if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python extract_features.py <TextGridFolder> <ConditionExcel> <OutputFolder>")
        sys.exit(1)

    textgrid_folder = sys.argv[1]
    condition_excel = sys.argv[2]
    output_folder = sys.argv[3]

    process_files(textgrid_folder, condition_excel, output_folder)