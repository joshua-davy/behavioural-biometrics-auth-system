import hashlib

VALID_ANIMALS = ["dog", "cat", "rabbit", "snake", "bird", "frog"]
VALID_COLOURS = ["red", "blue", "green", "pink", "yellow", "orange"]

def build_graphical_secret(animal, colour):
    # normalises before created fixed string to prevent format issues
    # and hash issues where frogred and frogr+red same hash
    animal = normalise_value(animal)
    colour = normalise_value(colour)
    return f"animal:{animal}|colour:{colour}"

def hash_graphical_secret(animal, colour):
    # encode converts string to bytes as sha requires this
    # hex returns readable hex instead of bytes
    secret = build_graphical_secret(animal, colour)
    return hashlib.sha256(secret.encode()).hexdigest()

def graphical_match(stored_hash, animal, colour):
    return stored_hash == hash_graphical_secret(animal, colour)

def normalise_value(value):
    return value.strip().lower()

# validates animal and colour and checks they are allowed, called before hash comparison
def valid_selection(animal, colour):
    animal = normalise_value(animal)
    colour = normalise_value(colour)
    return animal in VALID_ANIMALS and colour in VALID_COLOURS

# guard against invalid index before accessing list
def animal_from_index(index_text):
    if index_text not in ["0", "1", "2", "3", "4", "5"]:
        return ""
    return VALID_ANIMALS[int(index_text)]