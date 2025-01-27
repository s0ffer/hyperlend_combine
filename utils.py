import sys

from loguru import logger


logger.remove()
# Reformating logger, removing code stroke info
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level}</level> | <level>{message}</level>",
    colorize=True,
)
log = logger

def load_file(file_path, description):
    """
    Reads a file line by line, removing empty lines and returning the content as a list.

    Args:
        file_path (str): The path to the file to be read.
        description (str): A description of the data being loaded, used for logging purposes.

    Returns:
        list: A list of non-empty, stripped lines from the file.
        None: If the file is not found or an error occurs during reading.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = [line.strip() for line in file if line.strip()]
            logger.info(f'Imported {len(data)} {description}')
            return data
    except FileNotFoundError:
        print(f"File {file_path} was not found.")
        return None
    except Exception as e:
        print(f"Error while reading file: {e}")
        return None


def format_proxy(proxy: str) -> dict:
    """
    Formats a proxy string into a dictionary with connection details.

    Args:
        proxy (str): Proxy string in the format `http://username:password@server:port`.

    Returns:
        dict: A dictionary with proxy details:
            - "server" (str): Full server address (e.g., `http://server:port`).
            - "ip" (str): Proxy server IP or domain.
            - "port" (str): Proxy server port.
            - "username" (str): Proxy username.
            - "password" (str): Proxy password.
    """
    if proxy is not None:
        username_password, server_port = proxy.replace('http://', '').split('@')
        username, password = username_password.split(':')
        server, port = server_port.split(':')
        proxy = {
            "server": f"http://{server}:{port}",
            "ip": server,
            "port": port,
            "username": username,
            "password": password,
        }
    return proxy
