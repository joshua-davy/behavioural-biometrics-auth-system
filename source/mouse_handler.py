import json
import math

# deserialise JSON from db back to python list
# called during mouse profile retrieval , [] prevents crash
def parse_samples(raw):
    try:
        return json.loads(raw)
    except:
        return []

# registration , check attempts and click attempts
def valid_samples(samples, expected_attempts=3, expected_length=8):
    # validates full reg dataset, before processing
    # list must be 3 sets, containing 8 samples
    # returns false if fails
    if not isinstance(samples, list):
        return False
    if len(samples) != expected_attempts:
        return False

    for sample in samples:
        if not isinstance(sample, list):
            return False
        if len(sample) != expected_length:
            return False
    return True

# login, checks inner list only. just before login comparison
def valid_sample(sample, expected_length=8):
    if not isinstance(sample, list):
        return False
    if len(sample) != expected_length:
        return False

    return True


# takes registration samples and averages
def averagesList(samples):
    # positional averages across 3 reg attempts
    # so sess1[0] + sess2[0] / 2 etc
    length = len(samples[0])
    avg = []

    for i in range(length):
        vals = [s[i] for s in samples] # collect pos i from each attempt
        avg.append(round(sum(vals) / len(vals), 2))
    return avg

# takes registration samples and calcs std
# positional just like avg
def stdList(samples):
    length = len(samples[0])
    std = []

    for i in range(length):
        vals = [s[i] for s in samples]
        if len(vals) < 2:
            std.append(0.0)
        else:
            mean = sum(vals) / len(vals)
            variance = sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)
            variance = max(variance, 0.0)
            std.append(round(math.sqrt(variance), 2))

    return std

# json serial happens in app,py before database storage
# sqlite doesnt store python lists so needs text
def build_profile(samples):
    return {
        "avg_profile": averagesList(samples),
        "std_profile": stdList(samples)
    }

# compare login samples against stored profile
# epsolon prevents div by zero error if sig = 0
# not like sig_min which handles strictness
def mouse_statsRange(stored_profile, login_profile, epsilon=1e-6):
    stored_avg = stored_profile["avg_profile"]
    stored_std = stored_profile["std_profile"]
    login_avg = login_profile["avg_profile"]
    z_scores = {}
    z_values = []

    # mu = stored mean, x = login mean
    for i in range(len(stored_avg)):
        mu = stored_avg[i] # reg mean for pos
        x = login_avg[i] # login mean for pos
        sigma = max(stored_std[i], 20.0)
        z = abs(x - mu) / (sigma + epsilon)
        z_scores[f"transition_{i + 1}"] = round(z, 3)
        z_values.append(z)

    # sort values to index -2, get rid of 2 max values
    sorted_z_values = sorted(z_values)
    if len(sorted_z_values) > 2:
        trimmed_z_values = sorted_z_values[:-2]
    else:
        trimmed_z_values = sorted_z_values
    trim_avg_z = round(sum(trimmed_z_values) / len(trimmed_z_values), 3)
    trim_max_z = round(max(trimmed_z_values), 3)
    similarity = round(1 / (1 + trim_avg_z), 3)

    return trim_avg_z, trim_max_z, similarity, z_scores

