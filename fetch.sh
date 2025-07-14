REPO_NAME=$1

~/go/bin/goat repo export "$REPO_NAME"

LATEST_FILE="$(ls -1t "$REPO_NAME".*.car | head -n1)"
~/go/bin/goat repo unpack "$LATEST_FILE"

read -p "Delete old .car files? [y/N] " confirm
if [[ "$confirm" =~ ^[Yy]$ ]]; then
    find . -maxdepth 1 -name "$REPO_NAME.*.car" ! -name "$LATEST_FILE" -delete
fi

DID_DIR="$(~/go/bin/goat resolve $REPO_NAME | jq -r .id)"

# Threaded, quoted plain text in chronological order ideal for feeding into LLM
python3 thread_replies.py $DID_DIR > $REPO_NAME.txt

# Make .jsonl to load into Nomic Altas (atlas.nomic.ai)
python3 embed_atlas.py $DID_DIR > $REPO_NAME.jsonl

# Show monthly, weekday, and full calendar heatmap of posts
python3 bluesky_heatmap.py $DID_DIR
