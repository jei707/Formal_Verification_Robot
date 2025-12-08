"""
Simple script to test if the backend is running and accessible.
"""
import requests
import sys

API_URL = "http://127.0.0.1:5000/verify"

def test_connection():
    """Test if backend is accessible."""
    print("Testing backend connection...")
    print(f"Trying to connect to: {API_URL}")
    print("-" * 50)
    
    try:
        # Test home endpoint
        response = requests.get("http://127.0.0.1:5000/", timeout=2)
        print(f"✓ Home endpoint accessible: {response.status_code}")
        print(f"  Response: {response.text}")
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to backend server")
        print("\nThe backend server is not running or not accessible.")
        print("\nTo start the backend:")
        print("  1. Open a terminal/command prompt")
        print("  2. Navigate to the formalVerification directory")
        print("  3. Run: python app.py")
        print("\nYou should see: 'Server running on: http://127.0.0.1:5000'")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    
    try:
        # Test verify endpoint
        test_data = {"actions": ["poweron", "scanarea"]}
        response = requests.post(API_URL, json=test_data, timeout=5)
        print(f"✓ Verify endpoint accessible: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"  Summary: {data.get('summary', 'N/A')}")
            print("✓ Backend is working correctly!")
            return True
        else:
            print(f"  Error response: {response.text}")
            return False
    except Exception as e:
        print(f"✗ Error testing verify endpoint: {e}")
        return False

if __name__ == "__main__":
    success = test_connection()
    sys.exit(0 if success else 1)

