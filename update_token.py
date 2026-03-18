import sys
import os
from google_auth_oauthlib.flow import InstalledAppFlow

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

def main():
    channel = sys.argv[1] if len(sys.argv) > 1 else "tech"
    client_secrets = f"client_secrets_{channel}.json"
    token_file = f"youtube_token_{channel}.json"
    
    print(f"Starting authentication flow for {channel.capitalize()} channel...")
    print(f"Looking for: {client_secrets}")
    print(f"Will save to: {token_file}")

    if not os.path.exists(client_secrets):
        print(f"❌ {client_secrets} not found!")
        sys.exit(1)

    print("A browser window will open shortly. Please authenticate with the correct Google account.")
    flow = InstalledAppFlow.from_client_secrets_file(client_secrets, YOUTUBE_SCOPES)
    creds = flow.run_local_server(port=0)
    
    with open(token_file, "w") as f:
        f.write(creds.to_json())
    print(f"✅ {token_file} updated successfully!")

if __name__ == "__main__":
    main()
