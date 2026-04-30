import streamlit as st
import pandas as pd
from curl_cffi import requests
from bs4 import BeautifulSoup
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import io

# Initialize VADER sentiment analyzer
analyzer = SentimentIntensityAnalyzer()

# Function to scrape Flipkart reviews
def scrape_flipkart_reviews(url, pages):
    customer_names = []
    review_titles = []
    ratings = []
    comments = []

    for i in range(1, pages + 1):
        page_url = f"{url}&page={i}"
        # st.write(f"Fetching: {page_url}")

        retry_attempts = 2
        for attempt in range(retry_attempts):
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"
                }
                # session = requests.Session()

                # page = requests.get(page_url,timeout=3,verify=False)
                page = requests.get(page_url,impersonate="chrome")
                if page.status_code != 200:
                    st.write(f"Failed to fetch page {i}. Status code: {page.status_code}")
                    continue
                soup = BeautifulSoup(page.content, 'html.parser')

                # Extract customer names
                names = soup.find_all('p', class_='_2NsDsF AwS1CA')
                customer_names.extend(name.get_text() for name in names)
                # Extract review titles
                titles = soup.find_all('p', class_='z9E0IG')
                review_titles.extend(title.get_text() for title in titles)
                # Extract ratings
                ratings_divs = soup.find_all('div', class_='XQDdHH Ga3i8K')
                ratings.extend(r.get_text() for r in ratings_divs)
                # Extract comments
                comments_divs = soup.find_all('div', class_='ZmyHeo')
                comments.extend(c.div.div.get_text(strip=True) for c in comments_divs)

                if names or titles or ratings or comments:
                    break  # Exit retry loop if data is found

                if not names and not titles and not ratings and not comments:
                    st.write(f"No data found on page {i}.")
                

    min_length = min(len(customer_names), len(review_titles), len(ratings), len(comments))
    customer_names = customer_names[:min_length]
    review_titles = review_titles[:min_length]
    ratings = ratings[:min_length]
    comments = comments[:min_length]

    data = {
        'Customer Name': customer_names,
        'Review Title': review_titles,
        'Rating': ratings,
        'Comment': comments
    }

    df = pd.DataFrame(data)
    df['VADER Sentiment'] = df['Comment'].apply(lambda x: analyzer.polarity_scores(x)['compound'])
    return df

# Function to generate word cloud
def generate_wordcloud(text):
    wordcloud = WordCloud(width=800, height=400, background_color='white').generate(text)
    return wordcloud

# Function to extract words from word cloud
def extract_words_from_wordcloud(wordcloud):
    words = wordcloud.words_
    return list(words.keys())

# Streamlit app
def main():
    st.title("Flipkart Product Reviews Scraper and Analysis")

    url = st.text_input("Enter the product URL:", "https://www.flipkart.com/samsung-80-cm-32-inch-hd-ready-led-smart-tizen-tv-bezel-free-design/product-reviews/itm33b1495b9e937?pid=TVSGHY2UZA9YHWQN&lid=LSTTVSGHY2UZA9YHWQNCPAW6M&marketplace=FLIPKART")
    pages = st.number_input("Number of pages to scrape:", min_value=20, max_value=100, value=30)

    if 'df' not in st.session_state:
        st.session_state.df = None
    if 'positive_words' not in st.session_state:
        st.session_state.positive_words = []
    if 'negative_words' not in st.session_state:
        st.session_state.negative_words = []

    if st.button("Scrape Data"):
        st.session_state.df = scrape_flipkart_reviews(url, pages)
        if st.session_state.df is not None and not st.session_state.df.empty:
            st.write(f"Data collected from {pages} pages.")

            df = st.session_state.df
            positive_comments = ' '.join(df[df['VADER Sentiment'] > 0.1]['Comment'])
            negative_comments = ' '.join(df[df['VADER Sentiment'] < -0.1]['Comment'])

            st.subheader("Word Clouds")

            if positive_comments:
                positive_wc = generate_wordcloud(positive_comments)
                st.image(positive_wc.to_array(), caption='Positive Comments')
                st.session_state.positive_words = extract_words_from_wordcloud(positive_wc)[:20]
            else:
                st.write("No positive comments available for word cloud.")

            if negative_comments:
                negative_wc = generate_wordcloud(negative_comments)
                st.image(negative_wc.to_array(), caption='Negative Comments')
                st.session_state.negative_words = extract_words_from_wordcloud(negative_wc)[:20]
            else:
                st.write("No negative comments available for word cloud.")
        else:
            st.write("No data was scraped. Please check the URL and try again.")

    keyword = st.text_input("Enter keyword to search for in reviews:")
    rating_filter = st.selectbox("Select Rating (optional):", options=["All", "1", "2", "3", "4", "5"], index=0)
    sentiment_filter = st.selectbox("Select Sentiment (optional):", options=["All", "Positive", "Negative"], index=0)
    p = st.button("Search")

    selected_word = None

    with st.expander("Positive Words", expanded=True):
        if 'positive_words' in st.session_state:
            cols = st.columns(5)
            for index, word in enumerate(st.session_state.positive_words):
                col = cols[index % 5]
                if col.button(word, key=f"positive_button_{index}"):
                    selected_word = word

    with st.expander("Negative Words", expanded=True):
        if 'negative_words' in st.session_state:
            cols = st.columns(5)
            for index, word in enumerate(st.session_state.negative_words):
                col = cols[index % 5]
                if col.button(word, key=f"negative_button_{index}"):
                    selected_word = word

    if selected_word and st.session_state.df is not None:
        st.subheader(f"Comments containing the word: {selected_word}")
        df = st.session_state.df
        comments_df = df[df['Comment'].str.contains(selected_word, case=False)]
        for _, row in comments_df.iterrows():
            with st.expander(f"Comment by {row['Customer Name']}", expanded=True):
                st.write(f"**Rating:** {row['Rating']}")
                st.write(f"**Title:** {row['Review Title']}")
                st.write(f"**Comment:** {row['Comment']}")
                st.write(f"**Sentiment Score:** {row['VADER Sentiment']:.2f}")

    if p:
        if keyword and st.session_state.df is not None:
            df_filtered = st.session_state.df[st.session_state.df['Comment'].str.contains(keyword, case=False)]
            
            if rating_filter != "All":
                df_filtered = df_filtered[df_filtered['Rating'] == rating_filter]
            
            if sentiment_filter == "Positive":
                df_filtered = df_filtered[df_filtered['VADER Sentiment'] > 0.1]
            elif sentiment_filter == "Negative":
                df_filtered = df_filtered[df_filtered['VADER Sentiment'] < -0.1]

            if not df_filtered.empty:
                st.subheader(f"Showing results for '{keyword}' with selected filters:")
                for _, row in df_filtered.iterrows():
                    with st.expander(f"Comment by {row['Customer Name']}", expanded=True):
                        st.write(f"**Rating:** {row['Rating']}")
                        st.write(f"**Title:** {row['Review Title']}")
                        st.write(f"**Comment:** {row['Comment']}")
                        st.write(f"**Sentiment Score:** {row['VADER Sentiment']:.2f}")
            else:
                st.write("No results found matching the criteria.")

if __name__ == "__main__":
    main()