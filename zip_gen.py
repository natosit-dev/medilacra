import random
import pandas as pd
from uszipcode import SearchEngine

def generate_zip_list(n_per_state: int = 25) -> pd.DataFrame:
    """
    Generates a DataFrame of ZIP codes and their major cities for each US state.

    Args:
        n_per_state: The number of random ZIP codes to pull for each state.

    Returns:
        A pandas DataFrame with columns for 'zipcode', 'major_city', and 'state'.
    """
    # List of all 50 US state abbreviations
    us_states = [
        'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
        'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
        'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
        'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
        'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
    ]

    # Initialize the SearchEngine
    search = SearchEngine()
    
    # Store the results in a list of dictionaries
    all_zips = []

    print("Generating a list of ZIP codes for each state...")
    for state in us_states:
        # Get all ZIP codes for the current state
        # The `major_city` is an attribute of the `SimpleZipcode` object
        results = search.by_state(state=state)
        
        # Check if there are enough ZIP codes to sample
        if len(results) < n_per_state:
            # If not, use all available ZIP codes for that state
            sampled_zips = results
        else:
            # Randomly sample the desired number of ZIP codes
            sampled_zips = random.sample(results, n_per_state)

        # Extract the zipcode and major city for each sample
        for zipcode_obj in sampled_zips:
            all_zips.append({
                'zipcode': zipcode_obj.zipcode,
                'major_city': zipcode_obj.major_city,
                'state': state
            })
    
    # Convert the list to a pandas DataFrame
    df = pd.DataFrame(all_zips)
    return df

if __name__ == "__main__":
    # Generate the DataFrame
    zip_data = generate_zip_list()
    
    # Print the DataFrame to the console
    print("\nGenerated ZIP Codes and Major Cities:")
    print(zip_data)
    
    # You can also save the results to a CSV file
    file_path = "us_zips.csv"
    zip_data.to_csv(file_path, index=False)
    print(f"\nData successfully saved to {file_path}")
