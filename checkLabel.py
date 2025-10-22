from praatio import textgrid

def check_turns(textgrid_path):
    tg = textgrid.openTextgrid(textgrid_path, includeEmptyIntervals=False)
    if "turns" not in tg.tierNames:
        raise ValueError("No 'turns' tier found in TextGrid")
    turns_tier = tg.getTier("turns")
    entries = turns_tier.entries

    # Check if each label only occurs once
    label_counts = {}
    label_dup_found = False

    for entry in entries:
        label = entry[2]
        if label in label_counts:
            label_counts[label] += 1
            label_dup_found = True
        else:
            label_counts[label] = 1

    for label, count in label_counts.items():
        if count > 1:
            print(f"Label '{label}' occurs {count} times")
    
    if not label_dup_found:
        print("No duplicate labels found.")

    
    # nth (even number) label & n+1th (odd number) label should have the same numbering in their labels
    for i in range(0, len(entries) - 1, 2):
        q_label = entries[i][2]
        r_label = entries[i + 1][2]
        invalid_pairs = False

        if not (q_label.startswith("Q") and r_label.startswith("R")):
            print(f"Invalid labels at positions {entries[i][0]} and {entries[i + 1][0]}: {q_label}, {r_label}")
            invalid_pairs = True
        elif q_label[1:] != r_label[1:]:
            print(f"Mismatch: {q_label} vs {r_label} at positions {entries[i][0]} and {entries[i + 1][0]}")
            invalid_pairs = True

    if not invalid_pairs:
        print("All existing Q/R pairs are valid.")

    # Check if all Q/R pairs from Q/R010 to Q/R054 are present
    existing_labels = set([entry[2] for entry in entries])

    expected_pairs = []
    for i in range(1, 51):  # Q/R010 ~ Q/R500
        base = f"{i:02d}0"
        q_label = f"Q{base}"
        r_label = f"R{base}"
        expected_pairs.append((q_label, r_label))

        for j in range(1, 5):  # Q/R011-Q014 ~ Q/R051-Q054
            sub_q = f"Q{i:02d}{j}"
            sub_r = f"R{i:02d}{j}"
            expected_pairs.append((sub_q, sub_r))

    missing = []
    for q, r in expected_pairs:
        if q not in existing_labels or r not in existing_labels:
            missing.append((q, r))

    if missing:
        print(f"{len(missing)} missing pairs in total")
        for q, r in sorted(missing):
            q_status = "not found" if q not in existing_labels else "found"
            r_status = "not found" if r not in existing_labels else "found"
            print(f"{q} {q_status}, {r} {r_status}")
    else:
        print("All expected Q/R pairs found.")
    