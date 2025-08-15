#!/usr/bin/env python3
"""
AI Content Agent Pro - WordPress Focused Implementation
Automated content creation and WordPress publishing with Gemini AI
"""

import streamlit as st
import os
import json
import markdown
from datetime import datetime, timedelta
import requests
import base64
from pathlib import Path
import zipfile
import shutil
import re
from typing import Dict, Any, Optional, List, Tuple
import time
from dotenv import load_dotenv
import io # Import for image handling

# Load environment variables from .env file
load_dotenv()


class AdvancedPublisher:
    """Advanced publishing module for automated content deployment, focused on WordPress."""
    
    def __init__(self):
        self.wordpress_config = {}
        
    def setup_wordpress(self, site_url: str, username: str, password: str):
        """Setup WordPress REST API connection."""
        is_wpcom = 'wordpress.com' in site_url.lower()
        
        if is_wpcom:
            site_domain = site_url.replace('https://', '').replace('http://', '').rstrip('/')
            self.wordpress_config = {
                'site_url': site_url.rstrip('/'),
                'site_domain': site_domain,
                'username': username,
                'password': password,  # For WordPress.com, this is an access token
                'is_wpcom': True,
                'api_base': f'https://public-api.wordpress.com/rest/v1.1/sites/{site_domain}',
                'headers': {
                    'Content-Type': 'application/json', # Default content type
                    'Authorization': f'Bearer {password}'
                }
            }
        else:
            self.wordpress_config = {
                'site_url': site_url.rstrip('/'),
                'username': username,
                'password': password,
                'is_wpcom': False,
                'use_query_params': None, # Will be detected automatically
                'headers': {
                    'Content-Type': 'application/json', # Default content type
                    'Authorization': f'Basic {base64.b64encode(f"{username}:{password}".encode()).decode()}'
                }
            }
            
    def _get_api_url(self, endpoint: str) -> str:
        """Constructs the correct API URL based on permalink settings (for self-hosted WordPress)."""
        if not self.wordpress_config:
            raise ValueError("WordPress configuration not set.")
            
        if self.wordpress_config.get('is_wpcom'):
            # WordPress.com uses a fixed base + endpoint
            return f"{self.wordpress_config['api_base']}{endpoint}"
        else:
            # Self-hosted WordPress uses detected permalink structure
            site_url = self.wordpress_config['site_url']
            # Default to pretty permalinks if use_query_params is not explicitly True
            if self.wordpress_config.get('use_query_params', False): # This will be True if detected, otherwise False (default)
                return f"{site_url}/?rest_route={endpoint}"
            else:
                return f"{site_url}/wp-json{endpoint}"
            
    def test_wordpress_connection(self) -> Dict[str, Any]:
        """Test WordPress connection with fallback for sites without pretty permalinks."""
        if not self.wordpress_config:
            return {'success': False, 'error': 'WordPress not configured'}
        
        try:
            if self.wordpress_config.get('is_wpcom'):
                response = requests.get(
                    self._get_api_url("/"),
                    headers=self.wordpress_config['headers'],
                    timeout=10
                )
                
                if response.status_code == 200:
                    site_data = response.json()
                    return {
                        'success': True, 
                        'message': f"Connected to WordPress.com site: {site_data.get('name', 'Unknown')}"
                    }
                elif response.status_code == 403:
                    return {
                        'success': False, 
                        'error': 'WordPress.com site is private or in Coming Soon mode. Please make your site public first.'
                    }
                else:
                    return {
                        'success': False, 
                        'error': f"WordPress.com API error: {response.status_code} - {response.text}"
                    }
            else:
                headers_to_use = self.wordpress_config['headers'].copy()
                headers_to_use['Accept'] = 'application/json' # Ensure JSON is accepted for better error messages
                
                # Try pretty permalinks first
                pretty_url = self._get_api_url("/wp/v2/users/me") # This will currently use default self.wordpress_config['use_query_params'] which is None/False initially
                response = requests.get(pretty_url, headers=headers_to_use, timeout=10)
                
                if response.status_code == 404:
                    # Fallback to query parameter format
                    fallback_url = self.wordpress_config['site_url'] + "/?rest_route=/wp/v2/users/me"
                    response = requests.get(fallback_url, headers=headers_to_use, timeout=10)
                    
                    if response.status_code == 200:
                        user_data = response.json()
                        self.wordpress_config['use_query_params'] = True # Set it if this worked
                        return {
                            'success': True, 
                            'message': f"Connected as {user_data.get('name', 'Unknown')} (using query parameter format)"
                        }
                    elif response.status_code == 401:
                         return {
                            'success': False,
                            'error': 'Authentication failed. Please check your username and application password.'
                        }
                elif response.status_code == 200:
                    user_data = response.json()
                    self.wordpress_config['use_query_params'] = False # Set it if this worked
                    return {
                        'success': True, 
                        'message': f"Connected as {user_data.get('name', 'Unknown')}"
                    }
                elif response.status_code == 401:
                    return {
                        'success': False,
                        'error': 'Authentication failed. Please check your username and application password.'
                    }
                
                return {
                    'success': False, 
                    'error': f"WordPress API error: {response.status_code} - {response.text}. Check if REST API is enabled and credentials are correct."
                }
                    
        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Connection timed out. Please check the URL and your network connection.'}
        except requests.exceptions.RequestException as e:
            return {'success': False, 'error': f"Network error or invalid URL: {str(e)}"}
        except Exception as e:
            return {'success': False, 'error': str(e)}
            
    def _get_terms_robust(self, term_type: str) -> List[Dict[str, Any]]:
        """
        Fetches terms (categories/tags) for WordPress.
        Returns a list of {'id': int, 'name': str} dictionaries.
        """
        if self.wordpress_config.get('is_wpcom'):
            # For WP.com, fetching terms requires specific endpoints and might vary.
            # We explicitly decided not to fully support fetching terms list for WP.com
            # due to API complexities in this focused version.
            st.warning(f"Fetching {term_type} list is not fully supported for WordPress.com via this API configuration.")
            return []

        terms_list = []
        headers_to_use = self.wordpress_config['headers'].copy()
        headers_to_use['Accept'] = 'application/json' # Ensure JSON is accepted
        
        endpoint = f"/wp/v2/{term_type}" # e.g., /wp/v2/categories or /wp/v2/tags
        api_url = self._get_api_url(endpoint) # This call will now use the correct /?rest_route= format if detected

        try:
            response = requests.get(api_url, headers=headers_to_use, timeout=10)
            
            if response.status_code == 200:
                terms_data = response.json()
                for term in terms_data:
                    terms_list.append({'id': term['id'], 'name': term['name']})
            else:
                st.error(f"Failed to fetch {term_type} from {api_url}: {response.status_code} - {response.text}")
                return []

        except requests.exceptions.Timeout:
            st.error(f"Timed out fetching {term_type}. Check network or site responsiveness.")
            return []
        except requests.exceptions.RequestException as e:
            st.error(f"Network error fetching {term_type}: {e}")
            return []
        except json.JSONDecodeError:
            st.error(f"Failed to decode JSON from {term_type} response: {response.text}")
            return []
        except Exception as e:
            st.error(f"Error processing {term_type} data: {e}")
            
        return terms_list

    def fetch_categories(self) -> List[Dict[str, Any]]:
        """Fetches all existing categories from WordPress."""
        return self._get_terms_robust('categories')

    def fetch_tags(self) -> List[Dict[str, Any]]:
        """Fetches all existing tags from WordPress."""
        return self._get_terms_robust('tags')

    def upload_image_to_wordpress(self, image_data: bytes, filename: str, mime_type: str) -> Dict[str, Any]:
        """Uploads an image to the WordPress media library."""
        if not self.wordpress_config:
            return {'success': False, 'error': 'WordPress not configured'}

        if self.wordpress_config.get('is_wpcom'):
            # WordPress.com media upload is to /sites/{siteID}/media/new
            # This endpoint typically expects multipart/form-data with a file field.
            # The structure for WP.com media upload can be more complex than self-hosted.
            st.warning("WordPress.com image upload is more complex and not fully implemented for direct file upload in this version.")
            return {'success': False, 'error': 'WordPress.com image upload not fully supported in this version. Try self-hosted WP.'}

        try:
            media_api_url = self._get_api_url("/wp/v2/media")
            
            headers_to_use = self.wordpress_config['headers'].copy()
            # Crucially, set the Content-Type for the raw binary data
            headers_to_use['Content-Type'] = mime_type 
            # Add Content-Disposition header
            headers_to_use['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            response = requests.post(
                media_api_url,
                headers=headers_to_use,
                data=image_data, 
                timeout=30
            )

            if response.status_code == 201:
                media_info = response.json()
                return {
                    'success': True,
                    'media_id': media_info['id'],
                    'media_url': media_info['source_url'],
                    'message': f"Image '{filename}' uploaded successfully to media library."
                }
            else:
                return {
                    'success': False,
                    'error': f"Image upload failed: {response.status_code} - {response.text}"
                }

        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Image upload timed out. The WordPress site might be slow or unreachable.'}
        except requests.exceptions.RequestException as e:
            return {'success': False, 'error': f"Network error during image upload: {str(e)}"}
        except Exception as e:
            return {'success': False, 'error': f"Unexpected error during image upload: {str(e)}"}
            
    def publish_to_wordpress(self, title: str, content: str, status: str = 'draft', 
                           categories: List[str] = None, tags: List[str] = None, 
                           featured_image_id: Optional[int] = None) -> Dict[str, Any]:
        """Publish content to WordPress using REST API with permalink format detection and term ID handling."""
        if not self.wordpress_config:
            return {'success': False, 'error': 'WordPress not configured'}
        
        html_content = markdown.markdown(content, extensions=['codehilite', 'fenced_code'])
        
        try:
            post_data = {
                'title': title,
                'content': html_content,
                'status': status,
                'format': 'standard'
            }

            if featured_image_id:
                post_data['featured_media'] = featured_image_id
            
            if self.wordpress_config.get('is_wpcom'):
                if tags:
                    post_data['tags'] = ','.join(tags) 
                # Categories for WP.com still a bit tricky if not using direct IDs.
                # For now, will not attempt to set categories for WP.com via this method.
                if categories:
                    st.warning("Categories not directly supported for WordPress.com via this API version's post creation. Post will be uncategorized or default.")

                response = requests.post(
                    self._get_api_url("/posts/new"),
                    json=post_data,
                    headers=self.wordpress_config['headers'],
                    timeout=30
                )
                
                if response.status_code == 200:
                    post_info = response.json()
                    return {
                        'success': True,
                        'post_id': post_info['ID'],
                        'url': post_info['URL'],
                        'edit_url': f"{self.wordpress_config['site_url']}/wp-admin/post.php?post={post_info['ID']}&action=edit",
                        'message': f'Post published successfully to WordPress.com (Status: {status})'
                    }
                else:
                    return {
                        'success': False,
                        'error': f"WordPress.com API error: {response.status_code} - {response.text}"
                    }
                    
            else:
                # Self-hosted WordPress
                # Retrieve category and tag IDs based on names provided by the user
                if categories:
                    # st.session_state.wp_all_categories stores {'id': X, 'name': Y}
                    # We need to map user-selected names to their IDs
                    all_existing_categories = st.session_state.get('wp_all_categories', [])
                    selected_category_ids = [
                        cat['id'] for cat in all_existing_categories 
                        if cat['name'].lower() in [c.lower() for c in categories]
                    ]
                    if selected_category_ids:
                        post_data['categories'] = selected_category_ids
                    else:
                        st.warning(f"None of the specified categories ({', '.join(categories)}) were found or selected. Post will be uncategorized or default.")
                    
                if tags:
                    # Similar mapping for tags
                    all_existing_tags = st.session_state.get('wp_all_tags', [])
                    selected_tag_ids = [
                        tag['id'] for tag in all_existing_tags 
                        if tag['name'].lower() in [t.lower() for t in tags]
                    ]
                    if selected_tag_ids:
                        post_data['tags'] = selected_tag_ids
                    else:
                        st.warning(f"None of the specified tags ({', '.join(tags)}) were found or selected. Post will be published without specified tags.")
                
                api_url = self._get_api_url("/wp/v2/posts")
                
                response = requests.post(
                    api_url,
                    json=post_data,
                    headers=self.wordpress_config['headers'],
                    timeout=30
                )
                
                if response.status_code == 201:
                    post_info = response.json()
                    return {
                        'success': True,
                        'post_id': post_info['id'],
                        'url': post_info['link'],
                        'edit_url': f"{self.wordpress_config['site_url']}/wp-admin/post.php?post={post_info['id']}&action=edit",
                        'message': f'Post published successfully to WordPress (Status: {status})'
                    }
                else:
                    return {
                        'success': False,
                        'error': f"WordPress API error: {response.status_code} - {response.text}"
                    }
                    
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': 'WordPress publishing timed out. The WordPress site might be slow or unreachable.'
            }
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f"Network error during WordPress publishing: {str(e)}"
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"WordPress publishing error: {str(e)}"
            }


class CompleteAIContentAgent:
    def __init__(self):
        self.publisher = AdvancedPublisher()
        
        self.article_content_types = [
            "Blog Post",
            "Technical Article", 
            "Tutorial",
            "News Article",
            "Review",
            "Opinion Piece",
            "How-to Guide",
            "Case Study",
            "Product Documentation",
            "API Documentation",
            "White Paper",
            "Research Paper",
            "Marketing Copy",
        ]
        
        self.project_content_types = [
            "Python Project", "Web Application", "API Project", "Data Science Project",
            "Machine Learning Project", "Discord Bot", "Automation Script",
            "CLI Tool", "Game Project"
        ]
        
        self.writing_styles = [
            "Professional", "Casual", "Technical", "Conversational", "Academic",
            "Creative", "Formal", "Friendly", "Authoritative"
        ]
        
        self.target_audiences = [
            "Beginners", "Intermediate", "Advanced", "General Public", "Developers",
            "Business Professionals", "Students", "Researchers", "Decision Makers"
        ]
        
        self.word_counts = [
            "500-800", "800-1200", "1200-2000", "2000-3000", "3000-5000", "5000+"
        ]
        
    def setup_gemini(self, api_key: str) -> bool:
        """Setup Gemini AI API."""
        try:
            self.gemini_api_key = api_key
            test_result = self.call_gemini_api("Hello", api_key)
            if test_result and not test_result.startswith("Error:"):
                return True
            else:
                st.error(f"Gemini AI test failed: {test_result}")
                return False
        except Exception as e:
            st.error(f"Error initializing Gemini AI: {str(e)}")
            return False
    
    def call_gemini_api(self, prompt: str, api_key: str) -> str:
        """Call Gemini API using REST API."""
        chat_history = [{"role": "user", "parts": [{"text": prompt}]}]
        payload = {"contents": chat_history}
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

        try:
            response = requests.post(api_url, headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
            response.raise_for_status()
            result = response.json()

            if (result.get("candidates") and len(result["candidates"]) > 0 and 
                result["candidates"][0].get("content") and 
                result["candidates"][0]["content"].get("parts") and 
                len(result["candidates"][0]["content"]["parts"]) > 0):
                return result["candidates"][0]["content"]["parts"][0]["text"]
            else:
                return f"Error: No content generated. API Response: {json.dumps(result, indent=2)}"

        except requests.exceptions.RequestException as e:
            return f"Error making API request: {e}"
        except json.JSONDecodeError:
            return f"Error decoding JSON response: {response.text}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def generate_image_with_ai(self, prompt: str) -> Optional[bytes]:
        """
        Simulates AI image generation or provides a placeholder.
        In a real scenario, this would call an external image generation API.
        """
        st.info(f"Generating image for prompt: '{prompt}' (This is a placeholder, actual image generation requires external API integration like DALL-E, Stable Diffusion, etc.)")
        try:
            image_url = "https://via.placeholder.com/600x400?text=AI+Generated+Image"
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            st.error(f"Could not fetch placeholder image: {e}. Please check internet connection.")
            return None
        except Exception as e:
            st.error(f"Error in placeholder image generation: {e}")
            return None
    
    def generate_enhanced_content(self, topic: str, content_type: str, description: str, 
                                additional_requirements: str, writing_style: str, 
                                target_audience: str, word_count: str, 
                                include_seo: bool = True, include_toc: bool = False, 
                                include_examples: bool = True, include_conclusion: bool = True) -> Optional[str]:
        """Generate enhanced content with detailed parameters, adapting for content type."""
        
        seo_instructions = """
        SEO Requirements:
        - Include an engaging, keyword-rich title at the top (H1).
        - Use proper header hierarchy (H1, H2, H3, etc.).
        - Include relevant keywords naturally throughout the text.
        - Add a meta description-worthy introduction (first paragraph).
        - Ensure a strong conclusion with key takeaways.
        """ if include_seo else ""
        
        toc_instructions = """
        Table of Contents:
        - Generate a Table of Contents (TOC) at the beginning of the article, linking to main H2 sections.
        """ if include_toc else ""

        examples_instructions = """
        Examples and Practicality:
        - Incorporate practical examples, code snippets (if applicable), or real-world scenarios to illustrate concepts.
        - Ensure all code blocks are properly formatted with language identifiers (e.g., ```python).
        """ if include_examples else ""
        
        conclusion_instructions = """
        Conclusion:
        - Provide a concise summary of key points.
        - Offer actionable next steps or final thoughts.
        """ if include_conclusion else ""

        type_specific_instructions = ""
        if content_type == "Blog Post":
            type_specific_instructions = "Make it engaging, conversational, and shareable. Use relatable analogies. Focus on a strong hook and clear takeaways."
        elif content_type == "Tutorial" or content_type == "How-to Guide":
            type_specific_instructions = "Provide clear, step-by-step instructions. Include necessary prerequisites, detailed code examples (if applicable), and practical troubleshooting tips. The content should be highly actionable and easy to follow."
        elif content_type == "Technical Article":
            type_specific_instructions = "Dive deep into the technical aspects. Use precise terminology, comprehensive explanations of concepts, and detailed code/configuration examples. Assume a knowledgeable audience."
        elif content_type == "Review":
            type_specific_instructions = "Analyze the product/service comprehensively. Include a clear introduction, detailed pros and cons, target audience analysis, pricing insights (if applicable), and a clear recommendation or rating (e.g., '4.5/5 Stars')."
        elif content_type == "News Article":
            type_specific_instructions = "Report on a recent event or development. Follow journalistic principles: who, what, when, where, why, and how. Maintain an objective, informative tone. Include a clear headline and summary."
        elif content_type == "Case Study":
            type_specific_instructions = "Detail a specific problem, the solution implemented, and the measurable results achieved. Focus on data, methodology, and quantifiable outcomes. Structure as: Introduction, Problem, Solution, Results, Conclusion."
        elif content_type == "Product Documentation" or content_type == "API Documentation":
             type_specific_instructions = "Provide clear, concise, and accurate instructions for using a product or API. Include installation, usage examples, parameter descriptions, and error handling. Organize content logically for easy navigation."


        prompt = f"""
        Create a comprehensive and engaging {content_type.lower()} about "{topic}".
        
        Content Specifications:
        - Content Type: {content_type}
        - Topic: {topic}
        - Writing Style: {writing_style}
        - Target Audience: {target_audience}
        - Word Count Target: Approximately {word_count} words
        
        Special Requirements from User:
        {description}
        
        Additional Instructions from User:
        {additional_requirements}
        
        ---
        Formatting and Structural Guidelines:
        {seo_instructions}
        {toc_instructions}
        {examples_instructions}
        {conclusion_instructions}
        
        Type-Specific Guidance:
        {type_specific_instructions}
        
        General Structure Requirements:
        1. **Title**: Create an engaging, descriptive title (use # for H1)
        2. **Introduction**: Hook the reader and outline what they'll learn (first paragraph).
        3. **Main Content**: Use proper heading hierarchy (##, ###) for sections.
        4. **Code Examples**: Use proper markdown code blocks with language specification (e.g., ```python).
        5. **Lists**: Use bullet points or numbered lists where appropriate.
        6. **Tables**: Create tables when comparing data or features (if relevant).
        7. **Quotes/Callouts**: Use > for important quotes or callouts.
        8. **Links**: Include relevant links (use placeholder URLs like https://example.com).
        
        Content Quality Standards:
        - Make it informative and actionable.
        - Ensure accuracy and up-to-date information.
        - Make it engaging and easy to read.
        - Include troubleshooting tips where relevant (especially for tutorials).
        - Add best practices and common pitfalls to avoid.
        
        Please create content that is publication-ready and professionally formatted in Markdown.
        """
        
        try:
            if not hasattr(self, 'gemini_api_key'):
                return "Error: Gemini AI API key not configured"
                
            result = self.call_gemini_api(prompt, self.gemini_api_key)
            return result if result and not result.startswith("Error:") else result
        except Exception as e:
            st.error(f"Error generating content: {str(e)}")
            return None
    
    def generate_project_files(self, project_name: str, project_type: str, description: str, 
                              additional_requirements: str, target_audience: str,
                              project_complexity: str = "Intermediate", include_tests: bool = False,
                              include_docker: bool = False, include_ci_cd: bool = False,
                              include_docs: bool = True, create_examples: bool = True) -> Optional[Dict[str, str]]:
        """Generate multiple files for a complete project with enhanced parameters."""
        
        test_instructions = "\n5. Include unit tests for key functionalities (e.g., using unittest or pytest)." if include_tests else ""
        docker_instructions = "\n6. Provide a Dockerfile and docker-compose.yml for containerization." if include_docker else ""
        ci_cd_instructions = "\n7. Add a basic CI/CD configuration (e.g., GitHub Actions workflow)." if include_ci_cd else ""
        docs_instructions = "\n8. Ensure inline comments and docstrings are comprehensive. Create a separate `docs/` folder for additional documentation if needed." if include_docs else ""
        examples_instructions = "\n9. Include example usage or test files (e.g., `example.py`)." if create_examples else ""
        
        prompt = f"""
        Create a complete {project_type.lower()} called "{project_name}".
        
        Project Specifications:
        - Project Name: {project_name}
        - Project Type: {project_type}
        - Target Audience: {target_audience}
        - Complexity Level: {project_complexity}
        - Description: {description}
        - Additional Requirements: {additional_requirements}
        
        Please create a complete project structure with multiple files. Format your response as follows:
        
        FILE: filename.ext
        ```language
        [file content here]
        ```
        
        FILE: another_file.ext
        ```language
        [file content here]
        ```
        
        Requirements:
        1. Create a main Python file with complete, working code.
        2. Include `requirements.txt` with all necessary dependencies.
        3. Create a comprehensive `README.md` with setup instructions, usage, and project overview.
        4. Add a `.gitignore` file for Python projects.
        {test_instructions}
        {docker_instructions}
        {ci_cd_instructions}
        {docs_instructions}
        {examples_instructions}
        10. Add configuration files if needed (e.g., `config.py`, `.env.example`).
        
        Make sure all code is:
        - Production-ready and well-commented.
        - Follows best practices for the chosen language/framework.
        - Includes proper error handling.
        - Has clear documentation.
        - Is ready to run after setup.
        
        Focus on creating a {project_type.lower()} that is practical and useful.
        """
        
        try:
            if not hasattr(self, 'gemini_api_key'):
                return None
                
            result = self.call_gemini_api(prompt, self.gemini_api_key)
            
            if result and not result.startswith("Error:"):
                return self.parse_project_files(result)
            else:
                st.error(f"Project generation failed: {result}")
                return None
                
        except Exception as e:
            st.error(f"Error generating project: {str(e)}")
            return None
    
    def parse_project_files(self, content: str) -> Dict[str, str]:
        """Parse the AI response to extract individual files."""
        files = {}
        
        file_blocks_matches = re.findall(r'FILE:\s*([^\n]+)\n```(?:([a-zA-Z0-9]+))?\n(.*?)\n```', content, re.DOTALL)
        
        for filename, lang, file_content in file_blocks_matches:
            files[filename.strip()] = file_content.strip()

        if not files:
            st.warning("Could not parse files using strict FILE: and ``` markers. Attempting simpler parsing.")
            potential_files = re.split(r'(FILE:\s*[^\n]+)', content, flags=re.IGNORECASE)
            
            current_filename = None
            current_content = []

            for part in potential_files:
                if part.lower().startswith('file:'):
                    if current_filename and current_content:
                        files[current_filename] = "\n".join(current_content).strip()
                    current_filename = part.replace('FILE:', '').strip()
                    current_content = []
                else:
                    current_content.append(part)
            
            if current_filename and current_content:
                files[current_filename] = "\n".join(current_content).strip()
            
            for fname, fcontent in files.items():
                if fcontent.startswith('```') and fcontent.endswith('```'):
                    files[fname] = '\n'.join(fcontent.split('\n')[1:-1]).strip()
                elif fcontent.startswith('```'):
                    files[fname] = '\n'.join(fcontent.split('\n')[1:]).strip()

        if not files:
            project_name = "AI Generated Project"
            files['README.md'] = f"# {project_name}\n\nProject generated by AI Content Agent Pro"
            files['main.py'] = "# Main project file\nprint('Hello, World!')"
            files['requirements.txt'] = "# Add your dependencies here"
            st.error("Failed to parse any files from AI response. Generated minimal placeholder files.")
        
        return files
    
    def generate_seo_metadata(self, content: str, topic: str) -> Optional[Dict[str, Any]]:
        """Generate SEO metadata for the content."""
        
        content_preview = content[:1500] 
        
        prompt = f"""
        Based on this content about "{topic}", generate SEO metadata.
        
        Content Preview: {content_preview}...
        
        Please provide SEO-optimized metadata in this exact JSON format.
        Make sure the content adheres to length constraints and is highly relevant.
        {{
            "title": "SEO-optimized title (50-60 characters, avoid truncation)",
            "description": "Compelling meta description (150-160 characters, summarize key points, entice clicks)",
            "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
            "slug": "url-friendly-slug-with-hyphens"
        }}
        
        Guidelines:
        - **Title**: Include main keywords, be descriptive, engaging, and fit within 50-60 characters.
        - **Description**: Summarize the article, use strong verbs, include relevant keywords, and be between 150-160 characters.
        - **Keywords**: 3-5 relevant, high-impact keywords.
        - **Slug**: Lowercase, use hyphens instead of spaces, avoid special characters, be concise.
        """
        
        try:
            if not hasattr(self, 'gemini_api_key'):
                st.warning("Gemini AI API key not configured for SEO generation. Using fallback metadata.")
                return {
                    "title": topic[:60],
                    "description": f"Learn about {topic} in this comprehensive guide.",
                    "keywords": [topic.lower()],
                    "slug": topic.lower().replace(' ', '-').replace(',', '').replace('.', '')[:50]
                }
                
            response = self.call_gemini_api(prompt, self.gemini_api_key)
            
            if response and not response.startswith("Error:"):
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    try:
                        parsed_json = json.loads(json_match.group())
                        parsed_json['title'] = parsed_json.get('title', topic)[:60].strip()
                        parsed_json['description'] = parsed_json.get('description', f"Learn about {topic}").replace('\n', ' ')[:160].strip()
                        parsed_json['keywords'] = [k.strip().lower() for k in parsed_json.get('keywords', []) if k.strip()][:5]
                        parsed_json['slug'] = re.sub(r'[^\w\s-]', '', parsed_json.get('slug', topic).lower()).replace(' ', '-').strip()[:60]
                        return parsed_json
                    except json.JSONDecodeError:
                        st.warning(f"Could not parse SEO JSON from Gemini. Raw response: {response}. Using fallback metadata.")
                        pass
            
            st.warning("SEO generation failed or returned invalid format. Using fallback metadata.")
            return {
                "title": topic[:60],
                "description": f"Learn about {topic} in this comprehensive guide.",
                "keywords": [topic.lower()],
                "slug": topic.lower().replace(' ', '-').replace(',', '').replace('.', '')[:50]
            }
            
        except Exception as e:
            st.error(f"Error generating SEO metadata: {str(e)}")
            return {
                "title": topic[:60],
                "description": f"Learn about {topic} in this comprehensive guide.",
                "keywords": [topic.lower()],
                "slug": topic.lower().replace(' ', '-').replace(',', '').replace('.', '')[:50]
            }
    
    def extract_title_from_content(self, content: str) -> str:
        """Extract title from generated content (first H1)."""
        lines = content.split('\n')
        for line in lines:
            if line.startswith('#') and not line.startswith('##'):
                potential_title = line.replace('#', '').strip()
                potential_title = re.sub(r'[^\w\s]', '', potential_title).strip()
                return potential_title
        return "Generated Content"
    
    def save_markdown_file(self, content: str, title: str, seo_metadata: Dict = None) -> str:
        """Save content as markdown file with YAML front matter metadata."""
        output_dir = Path("generated_content")
        output_dir.mkdir(exist_ok=True)
        
        filename = re.sub(r'[^\w\s-]', '', title).strip()
        filename = re.sub(r'[-\s]+', '-', filename).lower()
        filepath = output_dir / f"{filename}.md"
        
        metadata_header = "---\n"
        metadata_header += f"title: {json.dumps(title)}\n" 
        metadata_header += f"date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        metadata_header += f"generated_by: AI Content Agent Pro\n"
        
        if seo_metadata:
            metadata_header += f"seo_title: {json.dumps(seo_metadata.get('title', ''))}\n"
            metadata_header += f"description: {json.dumps(seo_metadata.get('description', ''))}\n"
            keywords_str = ', '.join(seo_metadata.get('keywords', []))
            metadata_header += f"keywords: {json.dumps(keywords_str)}\n"
            metadata_header += f"slug: {json.dumps(seo_metadata.get('slug', ''))}\n"
        
        metadata_header += "---\n\n"
        
        content_lines = content.split('\n')
        if content_lines and content_lines[0].strip().startswith('#'):
            potential_ai_h1 = content_lines[0].strip()[1:].strip()
            if potential_ai_h1.lower() == title.lower():
                content = '\n'.join(content_lines[1:])
        
        markdown_content = metadata_header + content
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        return str(filepath)
    
    def create_html_website(self, content: str, title: str, seo_metadata: Dict = None) -> str:
        """Create a complete HTML website with the generated content."""
        
        output_dir = Path("generated_website")
        output_dir.mkdir(exist_ok=True)
        
        html_content = markdown.markdown(content, extensions=['codehilite', 'fenced_code', 'tables'])
        
        page_title = seo_metadata.get('title', title) if seo_metadata else title
        meta_description = seo_metadata.get('description', '') if seo_metadata else ''
        keywords = ', '.join(seo_metadata.get('keywords', [])) if seo_metadata else ''
        
        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_title}</title>
    <meta name="description" content="{meta_description}">
    <meta name="keywords" content="{keywords}">
    <meta name="author" content="AI Content Agent Pro">
    <meta property="og:title" content="{page_title}">
    <meta property="og:description" content="{meta_description}">
    <meta property="og:type" content="article">
    
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/styles/github.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/highlight.min.js"></script>
    
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background-color: #fafafa;
        }}
        
        .container {{
            background-color: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }}
        
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 15px;
            margin-bottom: 30px;
            font-size: 2.5em;
        }}
        
        h2 {{
            color: #34495e;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
            margin-top: 40px;
            margin-bottom: 20px;
        }}
        
        h3 {{
            color: #34495e;
            margin-top: 30px;
            margin-bottom: 15px;
        }}
        
        pre {{
            background-color: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 20px;
            overflow-x: auto;
            margin: 20px 0;
        }}
        
        code {{
            background-color: #f8f9fa;
            padding: 3px 6px;
            border-radius: 4px;
            font-family: 'SFMono-Regular', 'Monaco', 'Inconsolata', 'Liberation Mono', 'Courier New', monospace;
            font-size: 0.9em;
        }}
        
        pre code {{
            background-color: transparent;
            padding: 0;
        }}
        
        blockquote {{
            border-left: 4px solid #3498db;
            margin: 0;
            padding: 0 0 0 20px;
            font-style: italic;
            background-color: #f8f9fa;
            padding: 15px 20px;
            border-radius: 0 8px 8px 0;
        }}
        
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
        }}
        
        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}
        
        th {{
            background-color: #f2f2f2;
            font-weight: bold;
        }}
        
        .meta {{
            color: #7f8c8d;
            font-style: italic;
            border-top: 1px solid #ecf0f1;
            padding-top: 20px;
            margin-top: 40px;
            text-align: center;
        }}
        
        .toc {{
            background-color: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        
        .toc h3 {{
            margin-top: 0;
            color: #495057;
        }}
        
        .highlight {{
            background-color: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 4px;
            padding: 15px;
            margin: 20px 0;
        }}
        
        a {{
            color: #3498db;
            text-decoration: none;
        }}
        
        a:hover {{
            text-decoration: underline;
        }}
        
        img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
        }}
        
        .article-header {{
            text-align: center;
            margin-bottom: 40px;
        }}
        
        .publish-date {{
            color: #7f8c8d;
            font-size: 0.9em;
        }}
        
        @media (max-width: 768px) {{
            body {{
                padding: 10px;
            }}
            
            .container {{
                padding: 20px;
            }}
            
            h1 {{
                font-size: 2em;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="article-header">
            <div class="publish-date">Published on {datetime.now().strftime('%B %d, %Y')}</div>
        </div>
        
        {html_content}
        
        <div class="meta">
            <p><strong>Article Information</strong><br>
            Published on {datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}</p>
        </div>
    </div>
    
    <script>
        hljs.highlightAll();
        
        // Add copy buttons to code blocks
        document.querySelectorAll('pre code').forEach((block) => {{
            const button = document.createElement('button');
            button.innerText = 'Copy';
            button.style.float = 'right';
            button.style.margin = '5px';
            button.style.padding = '5px 10px';
            button.style.background = '#3498db';
            button.style.color = 'white';
            button.style.border = 'none';
            button.style.borderRadius = '4px';
            button.style.cursor = 'pointer';
            
            button.addEventListener('click', () => {{
                navigator.clipboard.writeText(block.textContent);
                button.innerText = 'Copied!';
                setTimeout(() => {{ button.innerText = 'Copy'; }}, 2000);
            }});
            
            block.parentNode.style.position = 'relative';
            block.parentNode.appendChild(button);
        }});
    </script>
</body>
</html>"""
        
        html_file = output_dir / "index.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_template)
        
        return str(html_file)


def main():
    """Main Streamlit application."""
    
    st.set_page_config(
        page_title="AI Content Agent Pro (WordPress Focused)",
        page_icon="🚀",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS
    st.markdown("""
    <style>
        .main-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 2rem;
            border-radius: 15px;
            color: white;
            text-align: center;
            margin-bottom: 2rem;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        
        .main-header h1 {
            margin: 0;
            font-size: 3rem;
            font-weight: bold;
        }
        
        .main-header p {
            margin: 0.5rem 0 0 0;
            font-size: 1.2rem;
            opacity: 0.9;
        }
        
        .feature-box {
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            padding: 1.5rem;
            border-radius: 12px;
            border-left: 6px solid #667eea;
            margin: 1rem 0;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        }
        
        .success-box {
            background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
            padding: 1.5rem;
            border-radius: 12px;
            border-left: 6px solid #28a745;
            margin: 1rem 0;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        }
        
        .metric-card {
            background: white;
            padding: 1.5rem;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            text-align: center;
            border: 1px solid #e9ecef;
        }
        
        .status-connected {
            color: #28a745;
            font-weight: bold;
        }
        
        .status-disconnected {
            color: #dc3545;
            font-weight: bold;
        }
        
        .platform-card {
            background: white;
            padding: 1rem;
            border-radius: 8px;
            border: 1px solid #e9ecef;
            margin: 0.5rem 0;
        }
        
        div.stButton > button {
            width: 100%;
            border-radius: 8px;
            border: none;
            padding: 0.5rem 1rem;
            font-weight: 500;
            transition: all 0.3s ease;
        }
        
        div.stButton > button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        
        .sidebar .sidebar-content {
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🚀 AI Content Agent Pro</h1>
        <p>WordPress-Focused Content Creation & Publishing with Gemini AI</p>
    </div>
    """, unsafe_allow_html=True)
    
    if 'agent' not in st.session_state:
        st.session_state.agent = CompleteAIContentAgent()
    
    agent = st.session_state.agent
    
    # Sidebar Configuration
    with st.sidebar:
        st.header("🔧 Configuration")
        
        env_gemini_key = os.getenv('GEMINI_API_KEY', '')
        env_wp_site_url = os.getenv('WP_SITE_URL', '')
        env_wp_username = os.getenv('WP_USERNAME', '')
        env_wp_app_password = os.getenv('WP_APP_PASSWORD', '')
        
        api_key = st.text_input(
            "🤖 Gemini AI API Key", # Changed label for clarity
            value=env_gemini_key,
            type="password", 
            help="Get your API key from https://aistudio.google.com/",
            placeholder="Enter your Gemini AI API key" if not env_gemini_key else "Loaded from .env file",
            key="gemini_api_key_input"
        )
        
        if api_key:
            if 'gemini_configured' not in st.session_state or st.session_state.gemini_configured_key != api_key: # Added check for key change
                if agent.setup_gemini(api_key):
                    st.session_state.gemini_configured = True
                    st.session_state.gemini_configured_key = api_key # Store the key that successfully configured
                    st.success("✅ Gemini AI Connected")
                else:
                    st.error("❌ Failed to connect to Gemini AI")
            else:
                st.success("✅ Gemini AI Connected")
        else:
            st.session_state.gemini_configured = False # Set to false if key is empty
            st.session_state.gemini_configured_key = None
            st.info("👆 Enter your Gemini AI API key to get started")
        
        if env_gemini_key:
            st.caption("🔄 API key loaded from .env file")
        
        st.divider()
        
        st.subheader("📡 Publishing Platforms")
        
        # WordPress Configuration
        with st.expander("🏢 WordPress", expanded=True): # Expanded by default
            st.markdown("**Choose your WordPress type:**")
            wp_type = st.radio(
                "WordPress Type",
                ["Self-hosted WordPress", "WordPress.com"],
                help="Select whether you're using a self-hosted WordPress site or WordPress.com",
                key="wp_type_radio"
            )
            
            if wp_type == "WordPress.com":
                st.info("⚠️ **WordPress.com Requirements:**\n- Your site must be **public** (not in Coming Soon mode)\n- You need a **Business plan** or higher for REST API access\n- Use an **access token** instead of password")
                
                wp_site = st.text_input(
                    "WordPress.com Site URL", 
                    placeholder="https://yoursite.com",
                    help="Your full WordPress.com site URL",
                    value=env_wp_site_url,
                    key="wpcom_site_url_input"
                )
                wp_user = st.text_input(
                    "Username",
                    placeholder="your-username",
                    key="wpcom_username_input"
                )
                wp_pass = st.text_input(
                    "Access Token", 
                    type="password",
                    help="Get access token from WordPress.com → My Sites → Manage → Marketing → Connections",
                    key="wpcom_pass_input"
                )

                if env_wp_site_url or env_wp_username or env_wp_app_password:
                    st.caption("🔄 WordPress credentials loaded from .env file (if set)")
                if wp_site and 'wordpress.com' not in wp_site.lower() and wp_site.strip():
                    st.warning("⚠️ This doesn't look like a WordPress.com URL")
            else:
                st.info("ℹ️ **Self-hosted WordPress Requirements:**\n- WordPress 4.7+ with REST API enabled\n- Use **Application Password** (not login password)\n- **Auto-detects permalink format** (works with/without pretty permalinks)")
                
                wp_site = st.text_input(
                    "Site URL", 
                    placeholder="https://yoursite.com",
                    help="Your self-hosted WordPress site URL",
                    value=env_wp_site_url, # Pre-filled for your site
                    key="self_hosted_site_url_input"
                )
                wp_user = st.text_input(
                    "Username",
                    placeholder="your-username",
                    value=env_wp_username,
                    key="self_hosted_username_input"
                )
                wp_pass = st.text_input(
                    "App Password", 
                    type="password",
                    help="Create Application Password in WordPress admin → Users → Profile → Application Passwords",
                    value=env_wp_app_password,
                    key="self_hosted_pass_input"
                )
            
            # Button for explicit connection test
            if st.button("🔗 Test WordPress Connection", key="test_wp_connection_button"):
                with st.spinner("Testing connection..."):
                    agent.publisher.setup_wordpress(wp_site, wp_user, wp_pass)
                    result = agent.publisher.test_wordpress_connection()
                    
                    if result['success']:
                        st.session_state.wp_configured = True
                        st.session_state.wp_site_type = wp_type 
                        st.success(f"✅ {result['message']}")
                        
                        # Store detected permalink type if self-hosted
                        if not agent.publisher.wordpress_config.get('is_wpcom'):
                            if agent.publisher.wordpress_config.get('use_query_params'):
                                st.info("🔧 **Detected**: Your site uses query parameter format for REST API")
                            else:
                                st.info("🔧 **Detected**: Your site uses pretty permalinks for REST API")
                            
                            # --- Fetch categories and tags on successful self-hosted connection ---
                            with st.spinner("Fetching categories and tags..."):
                                st.session_state.wp_all_categories = agent.publisher.fetch_categories()
                                st.session_state.wp_all_tags = agent.publisher.fetch_tags()
                                if st.session_state.wp_all_categories:
                                    st.success(f"Fetched {len(st.session_state.wp_all_categories)} categories.")
                                else:
                                    st.warning("Could not fetch any categories. Ensure categories exist and API permissions are correct.")
                                if st.session_state.wp_all_tags:
                                    st.success(f"Fetched {len(st.session_state.wp_all_tags)} tags.")
                                else:
                                    st.warning("Could not fetch any tags. Ensure tags exist and API permissions are correct.")

                        else: # WP.com
                            st.warning("Category and Tag fetching is not directly supported for WordPress.com via this application's API configuration yet.")
                    else:
                        st.session_state.wp_configured = False 
                        st.error(f"❌ {result['error']}")
                        
                        if 'Coming Soon' in result['error']:
                            st.markdown("Follow the instructions above to make your WordPress.com site public.")
                        elif '401' in result['error'] or 'Authentication failed' in result['error']:
                            st.markdown("Check your username and application password/access token.")
                        elif '404' in result['error']:
                            st.markdown("Ensure REST API is enabled and URL is correct. For self-hosted, also check permalink settings.")
                        st.warning("Click '🔗 Test WordPress Connection' manually if you change credentials.")
            
            # Display current status
            if 'wp_configured' in st.session_state and st.session_state.wp_configured:
                st.markdown('<p class="status-connected">🟢 WordPress Connected</p>', unsafe_allow_html=True)
            else:
                st.markdown('<p class="status-disconnected">🔴 WordPress Not Configured</p>', unsafe_allow_html=True)
        
        st.divider()
        st.subheader("📊 Platform Status")
        
        platforms_status = [
            ("Gemini AI", "gemini_configured"),
            ("WordPress", "wp_configured")
        ]
        
        for platform, key in platforms_status:
            status = "🟢 Connected" if key in st.session_state and st.session_state[key] else "🔴 Not Connected"
            st.markdown(f"**{platform}**: {status}")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📝 Content & Project Creation", "🚀 Publishing", "📊 Results", "⚙️ Settings"])
    
    with tab1:
        st.header("📝 Content & Project Creation Wizard")
        
        if 'gemini_configured' not in st.session_state or not st.session_state.gemini_configured:
            st.warning("⚠️ Please configure Gemini AI in the sidebar to continue.")
            return
        
        creation_type = st.radio(
            "What would you like to create?",
            ["📄 Content (Articles, Blog Posts, Documentation)", "🚀 Python Projects & Applications"],
            help="Choose between creating written content or complete coding projects",
            key="creation_type_radio"
        )
        
        is_project = "Projects" in creation_type
        
        col1, col2 = st.columns([3, 2])
        
        with col1:
            st.subheader("📋 Basic Information")
            
            if is_project:
                project_name = st.text_input(
                    "🚀 Project Name",
                    placeholder="e.g., Simple Chatbot with Flask",
                    help="Enter the name of your project",
                    key="project_name_input"
                )
                
                col1a, col1b = st.columns(2)
                with col1a:
                    project_type = st.selectbox("🛠️ Project Type", 
                        agent.project_content_types,
                        key="project_type_select")
                with col1b:
                    target_audience = st.selectbox("👥 Target Users", 
                        ["Beginners", "Intermediate", "Advanced", "Developers"],
                        key="project_audience_select")
                
                topic = project_name
                
            else: # Not a project, so it's article/blog content
                topic = st.text_input(
                    "📌 Article Topic",
                    placeholder="e.g., The Future of AI in Content Creation",
                    help="Enter the main topic or title for your content",
                    key="article_topic_input"
                )
                
                col1a, col1b = st.columns(2)
                with col1a:
                    content_type = st.selectbox("📄 Content Type", 
                        agent.article_content_types,
                        key="article_type_select")
                    writing_style = st.selectbox("✍️ Writing Style", 
                        agent.writing_styles,
                        key="writing_style_select")
                
                with col1b:
                    target_audience = st.selectbox("👥 Target Audience", 
                        agent.target_audiences,
                        key="audience_select")
                    word_count = st.selectbox("📏 Word Count", 
                        agent.word_counts,
                        key="word_count_select")
            
            st.divider()
            
            st.subheader("📄 Detailed Requirements & Structure")
            
            if is_project:
                description = st.text_area(
                    "📝 Project Description & Features",
                    placeholder="""Describe your project in detail:

🎯 Main Purpose:
• What should this project do?
• What problem does it solve?

🔧 Features to Include:
• User authentication: Implement login/registration.
• Database integration: Use SQLite for data storage.
• API endpoints: Define GET/POST for user data.

💻 Technical Requirements:
• Programming languages: Python 3.9+
• Frameworks: Flask
• Libraries: SQLAlchemy, requests
• User interface: REST API (no frontend needed)

📚 Additional Requirements:
• Comprehensive error handling for all API endpoints.
• Logging of user activities.
• Simple configuration using environment variables (.env.example).""",
                    height=300,
                    help="Provide detailed specifications for your project",
                    key="project_description_area"
                )
                
                additional_requirements = st.text_area(
                    "➕ Additional Specifications (Optional)",
                    placeholder="""Any other specific instructions for the AI:

• Performance goals: Aim for quick response times.
• Scalability: Design for future expansion (e.g., easy switch to PostgreSQL).
• Security: Basic API key authentication.
• Development environment setup details.""",
                    height=200,
                    key="project_additional_req_area"
                )
                
            else:
                description = st.text_area(
                    "📝 Detailed Description & Core Topics",
                    placeholder=f"""Describe your content requirements in detail for a {content_type.lower()} about "{topic}":

🎯 Main Topics to Cover:
• Introduction to [Concept]: Explain the basics.
• Step-by-step implementation guide: Show how to do X.
• Best practices for [Concept]: Provide actionable advice.

💻 Technical Requirements (if applicable):
• Programming language: Python (version, libraries)
• Specific code examples for: data processing, API calls.
• Command-line instructions for setup.

📊 Structure Preferences:
• Include an engaging introduction and a strong conclusion.
• Use at least 3 main sections (H2 headings).
• Include practical examples for each major point.
• Add a "Troubleshooting Common Issues" section.
• Use bullet points for lists and tables for comparisons.

🔍 SEO & Format:
• Primary keyword: "{topic.lower().replace(' ', '-')}"
• Secondary keywords: [list, up, to, 5]
• Include a call-to-action (e.g., "start your journey").""",
                    height=300,
                    help="Provide detailed instructions for the AI to create exactly what you need. Be specific about sections, examples, and tone.",
                    key="content_description_area"
                )
                
                additional_requirements = st.text_area(
                    "➕ Additional Requirements (Optional)",
                    placeholder="""Any other specific instructions for the AI:

🎨 Style & Tone:
• Professional but approachable, avoiding overly academic jargon.
• Maintain a consistent, encouraging tone.

📈 Special Elements:
• Include a compelling anecdote or real-world example.
• Suggest relevant external resources for further reading.
• Add a section on common pitfalls and how to avoid them.

🔗 References:
• Mention 2-3 prominent tools/libraries in the field.
• Suggest potential sub-topics for future articles.

📱 Format Specifics:
• Mobile-friendly formatting.
• Suggest a potential social media blurb (e.g., tweet).""",
                    height=200,
                    key="content_additional_req_area"
                )
            
            with st.expander("🔧 Advanced Generation Options", expanded=True):
                if not is_project:
                    col_adv_content1, col_adv_content2 = st.columns(2)
                    with col_adv_content1:
                        include_seo = st.checkbox("Include SEO optimization", value=True, help="AI will focus on keywords, headings, and meta-description elements.", key="include_seo_checkbox")
                        include_toc = st.checkbox("Generate Table of Contents", value=False, help="Adds a Table of Contents at the start of the article.", key="include_toc_checkbox")
                    with col_adv_content2:
                        include_examples = st.checkbox("Include Practical Examples", value=True, help="Encourage the AI to provide code snippets, real-world scenarios, etc.", key="include_examples_checkbox")
                        include_conclusion = st.checkbox("Include Actionable Conclusion", value=True, help="Ensure the article ends with key takeaways and next steps.", key="include_conclusion_checkbox")
                else: 
                    col_adv_project1, col_adv_project2 = st.columns(2)
                    with col_adv_project1:
                        project_complexity = st.selectbox("⚙️ Project Complexity", ["Simple", "Intermediate", "Advanced"], help="Influences the depth and scope of the generated project.", key="project_complexity_select")
                        include_tests = st.checkbox("Include Unit Tests", value=False, help="Generate basic unit tests for the project.", key="include_tests_checkbox")
                        include_docker = st.checkbox("Include Docker Setup", value=False, help="Generate Dockerfile and docker-compose.yml.", key="include_docker_checkbox")
                    with col_adv_project2:
                        create_examples = st.checkbox("Create Usage Examples", value=True, help="Generate example scripts or usage demonstrations.", key="create_examples_checkbox")
                        include_docs = st.checkbox("Include Detailed Documentation", value=True, help="Encourage more extensive inline comments and README details.", key="include_docs_checkbox")
                        include_ci_cd = st.checkbox("Include CI/CD Configuration", value=False, help="Generate basic CI/CD workflow (e.g., GitHub Actions).", key="include_ci_cd_checkbox")


        with col2:
            st.subheader("🎯 Creation Preview")
            
            if topic or (is_project and project_name):
                col2a, col2b = st.columns(2)
                with col2a:
                    st.metric("⏱️ Est. Gen Time", "30-180s")
                    st.metric("📊 Audience", target_audience)
                
                with col2b:
                    if is_project:
                        st.metric("📁 Files", "3-10+")
                        st.metric("⚙️ Complexity", project_complexity)
                    else:
                        st.metric("📝 Words", word_count)
                        st.metric("🎨 Style", writing_style)
                
                if is_project:
                    st.markdown("""
                    <div class="feature-box">
                    <h4>🚀 Project Features (AI Will Attempt)</h4>
                    <ul style="margin: 0; padding-left: 20px;">
                    <li>🐍 Core project logic files</li>
                    <li>📋 `requirements.txt`</li>
                    <li>📚 Comprehensive `README.md`</li>
                    <li>🔧 `.gitignore` and config files</li>
                    <li>🧪 Unit tests (optional)</li>
                    <li>🐳 Docker setup (optional)</li>
                    <li>🔄 CI/CD config (optional)</li>
                    </ul>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div class="feature-box">
                    <h4>✅ Content Quality & Structure (AI Will Attempt)</h4>
                    <ul style="margin: 0; padding-left: 20px;">
                    <li>🎯 SEO-optimized elements (title, meta desc, keywords)</li>
                    <li>📱 Clean, readable formatting</li>
                    <li>💻 Syntax-highlighted code blocks (if technical)</li>
                    <li>📊 Logical section hierarchy (H1, H2, H3)</li>
                    <li>🔗 Placeholder for relevant links</li>
                    <li>📈 Actionable insights & tips</li>
                    <li>📚 Optional Table of Contents</li>
                    </ul>
                    </div>
                    """, unsafe_allow_html=True)
                
                if is_project:
                    project_info_map = {
                        "Python Project": "A general-purpose Python application.",
                        "Web Application": "A functional web app, potentially with frontend/backend components.",
                        "API Project": "A RESTful API with defined endpoints.",
                        "Data Science Project": "Scripts and notebooks for data analysis/modeling.",
                        "Machine Learning Project": "Code for an ML model, including data processing.",
                        "Discord Bot": "A functional Discord bot with commands.",
                        "Automation Script": "A script to automate a specific task.",
                        "CLI Tool": "A command-line interface tool.",
                        "Game Project": "Basic code for a simple game."
                    }
                    st.info(f"**{project_type}**: {project_info_map.get(project_type, 'A customized project.')}")
                else:
                    content_info_map = {
                        "Blog Post": "An engaging, conversational article for your blog.",
                        "Technical Article": "An in-depth piece covering technical concepts.",
                        "Tutorial": "A step-by-step guide to teach a specific skill.",
                        "News Article": "A factual report on a current event.",
                        "Review": "An evaluation of a product or service.",
                        "Opinion Piece": "A subjective article expressing a viewpoint.",
                        "How-to Guide": "Practical instructions for achieving a task.",
                        "Case Study": "An analysis of a problem, solution, and results.",
                        "Product Documentation": "User guides and reference material for a product.",
                        "API Documentation": "Comprehensive guide for using an API.",
                        "White Paper": "An authoritative report on a specific topic, often for problem-solving.",
                        "Research Paper": "A structured, academic-style paper based on research.",
                        "Marketing Copy": "Persuasive content designed to promote something."
                    }
                    st.info(f"**{content_type}**: {content_info_map.get(content_type, 'A customized content piece.')}")
        
        st.divider()
        
        col_gen1, col_gen2, col_gen3 = st.columns([1, 2, 1])
        
        with col_gen2:
            if is_project:
                button_text = "🚀 Generate Project"
                input_check = project_name
                error_msg = "❌ Please enter a project name."
            else:
                button_text = "🚀 Generate Content"
                input_check = topic
                error_msg = "❌ Please enter a topic for your content."
            
            if st.button(button_text, type="primary", use_container_width=True, key="generate_button"):
                if not input_check.strip():
                    st.error(error_msg)
                elif len(input_check.strip()) < 5 and not description.strip():
                    st.error("❌ Please provide a more detailed topic/project name or description (at least 5 characters).")
                else:
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    try:
                        if is_project:
                            status_text.text("🤖 AI is analyzing your project requirements...")
                            progress_bar.progress(20)
                            time.sleep(1)
                            
                            status_text.text("🔨 Creating project structure and code...")
                            progress_bar.progress(40)
                            
                            project_files = agent.generate_project_files(
                                project_name=project_name,
                                project_type=project_type,
                                description=description, 
                                additional_requirements=additional_requirements, 
                                target_audience=target_audience,
                                project_complexity=project_complexity,
                                include_tests=include_tests,
                                include_docker=include_docker,
                                include_ci_cd=include_ci_cd,
                                include_docs=include_docs,
                                create_examples=create_examples
                            )
                            
                            if project_files:
                                progress_bar.progress(90)
                                status_text.text("📁 Finalizing project files...")
                                
                                st.session_state.generated_project = project_files
                                st.session_state.project_name = project_name
                                st.session_state.project_type = project_type
                                st.session_state.project_description = description
                                st.session_state.generation_time = datetime.now()
                                st.session_state.is_project = True
                                
                                progress_bar.progress(100)
                                status_text.text("✅ Project generated successfully!")
                                
                                file_count = len(project_files)
                                total_lines = sum(len(content.split('\n')) for content in project_files.values())
                                
                                st.success(f"""
                                🎉 **Project Generated Successfully!**
                                
                                📊 **Stats:**
                                - Files: {file_count}
                                - Total lines: {total_lines:,}
                                - Project type: {project_type}
                                """)
                                
                                st.balloons()
                                
                            else:
                                st.error("❌ Failed to generate project files.")
                                
                        else: # Generating content (articles, blogs, etc.)
                            status_text.text("🤖 AI is analyzing your content requirements...")
                            progress_bar.progress(20)
                            time.sleep(1)
                            
                            status_text.text("✍️ Creating your content...")
                            progress_bar.progress(50)
                            
                            content = agent.generate_enhanced_content(
                                topic=topic,
                                content_type=content_type,
                                description=description, 
                                additional_requirements=additional_requirements, 
                                writing_style=writing_style, 
                                target_audience=target_audience, 
                                word_count=word_count, 
                                include_seo=include_seo,
                                include_toc=include_toc,
                                include_examples=include_examples,
                                include_conclusion=include_conclusion
                            )
                            
                            if content and not content.startswith("Error:"):
                                progress_bar.progress(70)
                                status_text.text("🔍 Generating SEO metadata...")
                                
                                seo_metadata = agent.generate_seo_metadata(content, topic)
                                
                                progress_bar.progress(90)
                                status_text.text("📝 Finalizing content...")
                                
                                st.session_state.generated_content = content
                                st.session_state.content_title = agent.extract_title_from_content(content)
                                st.session_state.content_topic = topic
                                st.session_state.content_type = content_type
                                st.session_state.seo_metadata = seo_metadata
                                st.session_state.generation_time = datetime.now()
                                st.session_state.is_project = False
                                
                                progress_bar.progress(100)
                                status_text.text("✅ Content generated successfully!")
                                
                                word_count_actual = len(content.split())
                                
                                st.success(f"""
                                🎉 **Content Generated Successfully!**
                                
                                📊 **Stats:**
                                - Words: {word_count_actual:,}
                                - Characters: {len(content):,}
                                - Estimated reading time: {word_count_actual // 200} minutes
                                """)
                                
                                st.balloons()
                                
                            else:
                                st.error(f"❌ Content generation failed: {content}")
                        
                        time.sleep(2)
                        progress_bar.empty()
                        status_text.empty()
                        
                    except Exception as e:
                        st.error(f"❌ Error during generation: {str(e)}")
                        progress_bar.empty()
                        status_text.empty()
    
    with tab2:
        st.header("🚀 Publishing & Distribution")
        
        has_content = 'generated_content' in st.session_state
        has_project = 'generated_project' in st.session_state
        
        if not has_content and not has_project:
            st.info("👆 Generate content or a project in the first tab to continue.")
            return
        
        is_project = st.session_state.get('is_project', False)
        
        if is_project and has_project:
            st.subheader("🚀 Project Files")
            
            project_files = st.session_state.generated_project
            project_name = st.session_state.project_name
            
            with st.expander("📁 Project Files Preview", expanded=False):
                for filename, content in project_files.items():
                    st.markdown(f"**📄 {filename}**")
                    
                    ext = filename.split('.')[-1].lower()
                    if ext == 'py': language = 'python'
                    elif ext == 'md': language = 'markdown'
                    elif ext == 'json': language = 'json'
                    elif ext in ['yaml', 'yml']: language = 'yaml'
                    elif ext == 'txt': language = 'text'
                    elif ext == 'html': language = 'html'
                    elif ext == 'css': language = 'css'
                    elif ext == 'js': language = 'javascript'
                    elif ext == 'sh': language = 'bash'
                    elif ext == 'env': language = 'bash' 
                    else: language = 'text'
                    
                    display_content = content[:1000] + "\n..." if len(content) > 1000 else content
                    st.code(display_content, language=language)
                    st.divider()
            
            file_count = len(project_files)
            calculated_total_lines = sum(len(content.split('\n')) for content in project_files.values())
            
            col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
            
            with col_stat1: st.metric("📁 Files", file_count)
            with col_stat2: st.metric("📝 Total Lines", f"{calculated_total_lines:,}")
            with col_stat3: st.metric("🛠️ Project Type", st.session_state.project_type)
            with col_stat4: st.metric("📊 Generated", "Recently")
            
            st.divider()
            st.subheader("💾 Local Download Options")
            
            col_down1, col_down2 = st.columns(2)
            
            with col_down1:
                if st.button("📁 Download as ZIP", use_container_width=True, key="download_project_zip_button"):
                    import io
                    
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                        for filename, content in project_files.items():
                            zip_file.writestr(filename, content)
                    
                    zip_buffer.seek(0)
                    
                    st.download_button(
                        "⬇️ Download Project ZIP",
                        zip_buffer.getvalue(),
                        file_name=f"{project_name.replace(' ', '_').lower()}_project.zip",
                        mime='application/zip',
                        key="final_download_project_zip"
                    )
            
            with col_down2:
                if st.button("📄 View Files Individually", use_container_width=True, key="view_individual_files_button"):
                    st.session_state.show_individual_files = True
            
            if st.session_state.get('show_individual_files', False):
                st.subheader("📄 Individual File Downloads")
                for filename, content in project_files.items():
                    col_file1, col_file2 = st.columns([3, 1])
                    with col_file1:
                        st.write(f"**{filename}**")
                    with col_file2:
                        st.download_button(
                            "⬇️ Download",
                            content.encode('utf-8'), 
                            file_name=filename,
                            key=f"download_individual_{filename}"
                        )
        
        elif has_content:
            with st.expander("📖 Content Preview", expanded=False):
                st.markdown(st.session_state.generated_content)
            
            content_stats = {
                "Word Count": len(st.session_state.generated_content.split()),
                "Character Count": len(st.session_state.generated_content),
                "Reading Time": f"{len(st.session_state.generated_content.split()) // 200} min",
                "Content Type": st.session_state.get('content_type', 'Unknown')
            }
            
            col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
            
            with col_stat1: st.metric("📝 Words", f"{content_stats['Word Count']:,}")
            with col_stat2: st.metric("🔤 Chars", f"{content_stats['Character Count']:,}")
            with col_stat3: st.metric("📖 Read Time", content_stats['Reading Time'])
            with col_stat4: st.metric("📄 Type", content_stats['Content Type'])
            
            st.divider()
            
            if 'seo_metadata' in st.session_state and st.session_state.seo_metadata:
                st.subheader("🔍 SEO Optimization")
                
                seo = st.session_state.seo_metadata
                
                col_seo1, col_seo2 = st.columns(2)
                
                with col_seo1:
                    seo_title = st.text_input(
                        "📰 SEO Title", 
                        value=seo.get('title', ''),
                        help="Optimized title for search engines (50-60 characters)",
                        key="seo_title_input"
                    )
                    
                    url_slug = st.text_input(
                        "🔗 URL Slug", 
                        value=seo.get('slug', ''),
                        help="URL-friendly version of your title",
                        key="url_slug_input"
                    )
                
                with col_seo2:
                    meta_description = st.text_area(
                        "📝 Meta Description", 
                        value=seo.get('description', ''),
                        height=100,
                        help="Description for search results (150-160 characters)",
                        key="meta_description_area"
                    )
                    
                    current_keywords = seo.get('keywords', [])
                    if not isinstance(current_keywords, list):
                        current_keywords = []
                    
                    keywords = st.multiselect(
                        "🏷️ Keywords/Tags",
                        options=list(set(current_keywords + [k.strip() for k in st.session_state.get('content_topic', '').split(',') if k.strip()])), 
                        default=current_keywords[:5],
                        key="keywords_multiselect"
                    )
                
                if seo:
                    st.session_state.seo_metadata.update({
                        'title': seo_title,
                        'description': meta_description,
                        'slug': url_slug,
                        'keywords': keywords
                    })
            
            st.divider()
            
            st.subheader("⚡ Quick Actions & WordPress Publishing")
            
            col_actions, col_wp_publish = st.columns([1, 2])
            
            with col_actions:
                if st.button("💾 Save Markdown", use_container_width=True, key="save_markdown_button"):
                    try:
                        filepath = agent.save_markdown_file(
                            st.session_state.generated_content,
                            st.session_state.content_title,
                            st.session_state.get('seo_metadata')
                        )
                        st.success(f"✅ Saved: {filepath}")
                        with open(filepath, 'r', encoding='utf-8') as f:
                            st.download_button(
                                "⬇️ Download Markdown", f.read().encode('utf-8'),
                                file_name=Path(filepath).name, mime='text/markdown',
                                key="download_markdown_final"
                            )
                    except Exception as e:
                        st.error(f"❌ Error saving file: {str(e)}")
                
                if st.button("🌐 Create HTML File", use_container_width=True, key="create_html_button"):
                    try:
                        html_path = agent.create_html_website(
                            st.session_state.generated_content,
                            st.session_state.content_title,
                            st.session_state.get('seo_metadata')
                        )
                        st.success(f"✅ HTML file created: {html_path}")
                        with open(html_path, 'r', encoding='utf-8') as f:
                            st.download_button(
                                "⬇️ Download HTML", f.read().encode('utf-8'),
                                file_name="index.html", mime='text/html',
                                key="download_html_final"
                            )
                    except Exception as e:
                        st.error(f"❌ Error creating HTML: {str(e)}")
            
            with col_wp_publish:
                if 'wp_configured' in st.session_state and st.session_state.wp_configured:
                    st.markdown("#### WordPress Publishing Options")
                    publish_status = st.selectbox("Post Status", ["draft", "publish"], key="wp_publish_status_select")
                    
                    # --- Categories & Tags Multiselect based on fetched terms ---
                    all_categories_names = [cat['name'] for cat in st.session_state.get('wp_all_categories', [])]
                    selected_categories = st.multiselect(
                        "Select Categories",
                        options=all_categories_names,
                        default=[],
                        help="Select existing categories from your WordPress site.",
                        key="categories_multiselect_wp"
                    )

                    all_tags_names = [tag['name'] for tag in st.session_state.get('wp_all_tags', [])]
                    # Suggest keywords from SEO metadata as default selection
                    default_tags = [
                        tag_name for tag_name in all_tags_names
                        if tag_name.lower() in [k.lower() for k in st.session_state.get('seo_metadata', {}).get('keywords', [])]
                    ]
                    selected_tags = st.multiselect(
                        "Select Tags",
                        options=all_tags_names,
                        default=default_tags,
                        help="Select existing tags from your WordPress site. Keywords from SEO are pre-selected if they exist as tags.",
                        key="tags_multiselect_wp"
                    )
                    # --- END Categories & Tags Multiselect ---

                    st.markdown("##### Featured Image (Optional)")
                    featured_image_option = st.radio(
                        "How to add Featured Image?",
                        ["None", "Manual Upload", "AI Generated"],
                        key="featured_image_option",
                        horizontal=True
                    )
                    
                    uploaded_file = None
                    ai_image_prompt = ""
                    featured_image_data = None 
                    featured_image_filename = None
                    featured_image_mime_type = None

                    if featured_image_option == "Manual Upload":
                        uploaded_file = st.file_uploader("Upload Image", type=["png", "jpg", "jpeg", "gif"], key="image_uploader")
                        if uploaded_file is not None:
                            featured_image_data = uploaded_file.getvalue()
                            featured_image_filename = uploaded_file.name
                            featured_image_mime_type = uploaded_file.type
                            st.image(uploaded_file, caption='Uploaded Image', width=200)

                    elif featured_image_option == "AI Generated":
                        ai_image_prompt = st.text_input("Describe Image for AI", placeholder="e.g., a futuristic city at sunset", key="ai_image_prompt")
                        if ai_image_prompt and st.button("Generate Image with AI", key="generate_ai_image_button"):
                            with st.spinner("Generating image... (This is a placeholder)"):
                                generated_image_bytes = agent.generate_image_with_ai(ai_image_prompt)
                                if generated_image_bytes:
                                    st.session_state.generated_ai_image_data = generated_image_bytes # Store data
                                    st.session_state.generated_ai_image_filename = f"ai_generated_{ai_image_prompt.replace(' ', '_')[:20]}.png"
                                    st.session_state.generated_ai_image_mime = "image/png"
                                    st.image(io.BytesIO(generated_image_bytes), caption='AI Generated Image', width=200)
                                else:
                                    st.error("Failed to generate AI image.")
                        # Display last generated image if exists and option is AI Generated
                        if 'generated_ai_image_data' in st.session_state and featured_image_option == "AI Generated":
                            featured_image_data = st.session_state.generated_ai_image_data
                            featured_image_filename = st.session_state.generated_ai_image_filename
                            featured_image_mime_type = st.session_state.generated_ai_image_mime
                            st.image(io.BytesIO(featured_image_data), caption='AI Generated Image (from session)', width=200)


                    if st.button("📝 Publish Post to WordPress", type="primary", use_container_width=True, key="publish_post_wp_button"):
                        if not st.session_state.get('wp_configured', False):
                            st.error("❌ WordPress is not configured. Please set up your credentials in the sidebar and test the connection.")
                            return
                        
                        featured_media_id = None
                        if featured_image_option != "None" and featured_image_data:
                            with st.spinner("Uploading featured image to WordPress media library..."):
                                upload_result = agent.publisher.upload_image_to_wordpress(
                                    featured_image_data, 
                                    featured_image_filename, 
                                    featured_image_mime_type
                                )
                                if upload_result['success']:
                                    st.success(f"✅ {upload_result['message']}")
                                    featured_media_id = upload_result['media_id']
                                else:
                                    st.error(f"❌ Failed to upload featured image: {upload_result['error']}")
                                    st.warning("Proceeding to publish post without featured image.")
                        elif featured_image_option != "None" and not featured_image_data:
                            st.warning("No image data available for featured image. Please upload/generate an image first.")
                            # Do not return here, let the post publish without image if user chose option but no image data.

                        with st.spinner("Publishing content to WordPress..."):
                            result = agent.publisher.publish_to_wordpress(
                                st.session_state.content_title,
                                st.session_state.generated_content,
                                status=publish_status,
                                categories=selected_categories, # Pass selected names
                                tags=selected_tags,         # Pass selected names
                                featured_image_id=featured_media_id
                            )
                            
                            if result['success']:
                                st.success(f"✅ Content published successfully to WordPress!")
                                st.markdown(f"🔗 **View Post:** {result['url']}")
                                st.markdown(f"✏️ **Edit Post:** {result['edit_url']}")
                                
                                if 'publish_results' not in st.session_state:
                                    st.session_state.publish_results = []
                                st.session_state.publish_results.append({
                                    'platform': 'WordPress',
                                    'status': 'success',
                                    'url': result['url'],
                                    'edit_url': result['edit_url'],
                                    'timestamp': datetime.now()
                                })
                            else:
                                st.error(f"❌ WordPress Publishing Error: {result['error']}")
                                
                else:
                    st.warning("WordPress is not configured. Please set up your credentials in the sidebar to enable publishing.")
                    st.button("📝 Configure WordPress", use_container_width=True, disabled=True, key="configure_wp_disabled_button_main")
            
            st.divider()
            st.subheader("🎯 Advanced Publishing Options")
            st.info("Additional publishing options (e.g., to other platforms) have been removed to focus on WordPress as per your request.")
            

    with tab3:
        st.header("📊 Publishing Results & Analytics")
        
        if 'publish_results' in st.session_state and st.session_state.publish_results:
            st.subheader("📈 Recent Publications")
            
            wordpress_results = [res for res in st.session_state.publish_results if res['platform'] == 'WordPress']
            
            if wordpress_results:
                for i, result in enumerate(reversed(wordpress_results)):
                    display_title = st.session_state.get('content_title', 'Untitled Post')
                    if len(display_title) > 70:
                        display_title = display_title[:67] + "..."

                    # >>> THIS IS THE LINE TO CHANGE <<<
                    with st.expander(f"WordPress - {display_title} ({result['timestamp'].strftime('%Y-%m-%d %H:%M')})", expanded=(i==0)): # REMOVE 'key' HERE
                        col_result1, col_result2 = st.columns([2, 1])
                        
                        with col_result1:
                            st.write(f"**Platform:** {result['platform']}")
                            st.write(f"**Status:** {'✅ Success' if result['status'] == 'success' else '❌ Failed'}")
                            st.write(f"**Published:** {result['timestamp'].strftime('%Y-%m-%d at %H:%M:%S')}")
                            
                            if 'url' in result:
                                st.markdown(f"🔗 [View Published Content]({result['url']})")
                                if 'edit_url' in result:
                                    st.markdown(f"✏️ [Edit in WordPress Admin]({result['edit_url']})")

                        with col_result2:
                            # You might still need keys for buttons inside loops
                            if st.button(f"📋 Copy URL", key=f"copy_url_btn_{i}"): # Add a unique key to the button
                                if 'url' in result:
                                    st.clipboard(result['url'])
                                    st.success("URL copied to clipboard!")
            else:
                st.info("📝 No WordPress publications yet. Publish some content to see results here!")
        else:
            st.info("📝 No publications yet. Publish some content to see results here!")
        
        if 'generated_content' in st.session_state or 'generated_project' in st.session_state:
            st.divider()
            st.subheader("📊 Content Analytics")
            
            if 'generated_content' in st.session_state:
                content = st.session_state.generated_content
                
                col_analytics1, col_analytics2, col_analytics3, col_analytics4 = st.columns(4)
                
                with col_analytics1: st.metric("📝 Total Words", f"{len(content.split()):,}")
                with col_analytics2: st.metric("📄 Paragraphs", len([p for p in content.split('\n\n') if p.strip()]))
                with col_analytics3: st.metric("💻 Code Blocks", len(re.findall(r'```[\s\S]*?```', content)))
                with col_analytics4: st.metric("📑 Headings", len(re.findall(r'^#+\s', content, re.MULTILINE)))
            
            elif 'generated_project' in st.session_state:
                project_files = st.session_state.generated_project
                
                col_analytics1, col_analytics2, col_analytics3, col_analytics4 = st.columns(4)
                
                with col_analytics1: st.metric("📁 Total Files", len(project_files))
                calculated_total_lines = sum(len(content.split('\n')) for content in project_files.values())
                with col_analytics2: st.metric("📝 Total Lines", f"{calculated_total_lines:,}")
                with col_analytics3: st.metric("🐍 Python Files", len([f for f in project_files.keys() if f.endswith('.py')]))
                with col_analytics4: st.metric("⚙️ Config Files", len([f for f in project_files.keys() if f in ['requirements.txt', 'README.md', '.gitignore', 'config.py', 'LICENSE']])) # Added LICENSE
            
            if 'seo_metadata' in st.session_state and st.session_state.seo_metadata:
                st.divider()
                st.subheader("🔍 SEO Analysis")
                
                seo = st.session_state.seo_metadata
                
                col_seo_analysis1, col_seo_analysis2 = st.columns(2)
                
                with col_seo_analysis1:
                    title_length = len(seo.get('title', ''))
                    title_status = "✅ Good" if 50 <= title_length <= 60 else "⚠️ Needs optimization"
                    st.metric("📰 Title Length", f"{title_length} chars", delta=title_status)
                    
                    st.metric("🏷️ Keywords", len(seo.get('keywords', [])))
                
                with col_seo_analysis2:
                    desc_length = len(seo.get('description', ''))
                    desc_status = "✅ Good" if 150 <= desc_length <= 160 else "⚠️ Needs optimization"
                    st.metric("📝 Description Length", f"{desc_length} chars", delta=desc_status)
                    
                    st.metric("🔗 URL Slug Length", f"{len(seo.get('slug', ''))} chars")
    
    with tab4:
        st.header("⚙️ Settings & Configuration")
        
        st.subheader("🔧 API Configuration")
        with st.expander("📋 API Information & Setup", expanded=True):
            st.markdown("""
            **Required API for Full Functionality:**
            
            1. **🤖 Google Gemini AI** (Required)
               - Get API key: [Google AI Studio](https://aistudio.google.com/)
               - Used for: Content generation and project creation
               - Cost: Free tier available
            
            2. **🏢 WordPress REST API** (Optional)
               - Setup: Ensure REST API is enabled in WordPress (default for modern versions).
               - **Self-hosted**: Create an **Application Password** in your WordPress admin via Users → Profile → Application Passwords. Use this password, not your regular login password.
               - **WordPress.com**: You'll need a **Business plan** or higher for full REST API access. Use an **Access Token** (from WordPress.com → My Sites → Manage → Marketing → Connections) instead of a password.
               - Used for: Direct WordPress publishing of generated content.
            """)
        
        st.divider()
        st.subheader("💾 Configuration Management")
        
        col_config1, col_config2 = st.columns(2)
        
        with col_config1:
            st.markdown("**📤 Export Current Preferences**")
            if st.button("📋 Generate Config File", key="generate_config_file_button"):
                config_template = {
                    "content_preferences": {
                        "default_writing_style": "Professional",
                        "default_target_audience": "Intermediate",
                        "default_word_count": "1200-2000",
                        "include_seo": True,
                        "include_toc": False,
                        "include_examples": True,
                        "include_conclusion": True
                    },
                    "project_preferences": {
                        "default_project_type": "Python Project",
                        "project_complexity": "Intermediate",
                        "include_tests": False,
                        "include_docker": False,
                        "include_ci_cd": False,
                        "include_documentation": True,
                        "create_examples": True
                    },
                    "publishing_platforms": {
                        "wordpress": {
                            "site_url": agent.publisher.wordpress_config.get('site_url', 'https://your-site.com'),
                            "username": agent.publisher.wordpress_config.get('username', 'your-username'),
                            "is_wpcom": agent.publisher.wordpress_config.get('is_wpcom', False),
                            "default_status": "draft"
                        }
                    },
                    "gemini_api_key_placeholder": "YOUR_GEMINI_API_KEY_HERE"
                }
                
                config_json = json.dumps(config_template, indent=2)
                
                st.download_button(
                    "⬇️ Download Config JSON",
                    config_json,
                    file_name="ai_agent_config.json",
                    mime="application/json",
                    key="download_config_json_button"
                )
        
        with col_config2:
            st.markdown("**📥 Import Settings**")
            uploaded_config = st.file_uploader(
                "Upload Configuration File (.json)",
                type=['json'],
                help="Upload a configuration JSON file to load preferences.",
                key="upload_config_file_uploader"
            )
            
            if uploaded_config:
                try:
                    config_data = json.load(uploaded_config)
                    
                    if 'content_preferences' in config_data:
                        st.session_state.default_content_prefs = config_data['content_preferences']
                    if 'project_preferences' in config_data:
                        st.session_state.default_project_prefs = config_data['project_preferences']
                    if 'publishing_platforms' in config_data and 'wordpress' in config_data['publishing_platforms']:
                        wp_cfg = config_data['publishing_platforms']['wordpress']
                        if 'site_url' in wp_cfg and 'username' in wp_cfg:
                            agent.publisher.setup_wordpress(wp_cfg['site_url'], wp_cfg['username'], "placeholder_password") 
                            st.session_state.wp_configured = True 
                            st.success("✅ WordPress configuration partially loaded (password/token needs re-entry).")
                    
                    st.success("✅ Configuration preferences loaded successfully!")
                    st.json(config_data)
                except Exception as e:
                    st.error(f"❌ Error loading configuration: {str(e)}")
        
        st.divider()
        st.subheader("ℹ️ Application Information")
        
        col_info1, col_info2 = st.columns(2)
        
        with col_info1:
            st.markdown("""
            **🚀 AI Content Agent Pro**
            
            - **Version:** 2.1.0 (WordPress Focused)
            - **Framework:** Streamlit
            - **AI Model:** Google Gemini 2.0 Flash
            - **Language:** Python 3.8+
            - **Key Features:** Content & Project Generation, WordPress Publishing
            """)
        
        with col_info2:
            wordpress_pub_count = len([r for r in st.session_state.get('publish_results', []) if r['platform'] == 'WordPress'])
            st.markdown(f"""
            **📊 Session Statistics**
            
            - **Content Generated:** {1 if 'generated_content' in st.session_state else 0}
            - **Projects Generated:** {1 if 'generated_project' in st.session_state else 0}
            - **WordPress Connected:** {'Yes' if st.session_state.get('wp_configured', False) else 'No'}
            - **Successful WP Publications:** {wordpress_pub_count}
            """)
        
        st.divider()
        st.subheader("🧹 Session Management")
        
        if st.button("🗑️ Clear All Session Data", key="clear_session_data_button", type="secondary"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.success("✅ All session data cleared! Please refresh the page or rerun the script.")
            st.experimental_rerun() # Use experimental_rerun for full state clear and reload

        st.divider()
        st.subheader("📚 Quick Help")
        
        with st.expander("🆘 Common Issues & Solutions", expanded=True):
            st.markdown("""
            **Common Problems & Solutions:**
            
            1.  **Gemini AI API Connection Failed:**
                * Double-check your API key for typos.
                * Ensure your internet connection is stable.
                * Verify your API key is active and has the necessary permissions in [Google AI Studio](https://aistudio.google.com/).
                
            2.  **WordPress Connection Failed:**
                * **Self-hosted:** Ensure you are using an **Application Password** (created in WordPress admin → Users → Profile) and **NOT** your regular login password.
                * **WordPress.com:** Confirm your site is **Public** (not "Coming Soon") and you have a **Business plan** or higher for REST API access. Use an **Access Token** (from WordPress.com → My Sites → Manage → Marketing → Connections).
                * Verify your WordPress site URL is correct and accessible from where this app is running.
                * Check if WordPress REST API is enabled (usually default for WP 4.7+).
                
            3.  **WordPress Publishing Failed (e.g., "Invalid parameter(s): tags" or categories not recognized):**
                * For **self-hosted WordPress**, tags and categories **must exist** on your WordPress site *before* you publish. The app tries to convert names to IDs by fetching available terms. If a name doesn't exist or doesn't exactly match (case-insensitive), it won't be applied. Create them manually in WordPress first.
                * For WordPress.com, tags are sent as names. Categories are often harder to set via API directly without specific IDs or plugins.
                
            4.  **Featured Image Upload Failed:**
                * Ensure your WordPress user (associated with the Application Password/Access Token) has permissions to upload media.
                * Check for file size limits on your WordPress server (PHP `upload_max_filesize`, `post_max_size`).
                * Verify the image file type is supported by WordPress.
                * **For AI-generated images:** This feature uses a placeholder. Actual AI image generation requires integration with a dedicated image generation API (e.g., DALL-E, Stable Diffusion) and their respective API keys.
                
            5.  **Generated Content/Project is too short or irrelevant:**
                * Provide a **more detailed and specific "Description"** and "Additional Requirements" in the "Content & Project Creation" tab.
                * Experiment with different "Writing Styles" or "Target Audiences."
                * Increase the "Word Count" target.
            """)


if __name__ == "__main__":
    main()