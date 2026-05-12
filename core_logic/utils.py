import time
from functools import wraps

PROF_DATA = {}  # Pour le profiling, si vous le gardez

def timing_decorator(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        print(f"Lancement de la fonction : {func_name}")
        if func_name not in PROF_DATA:
            PROF_DATA[func_name] = {'calls': 0, 'total_time': 0, 'details': {}}

        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        elapsed_time = end_time - start_time

        PROF_DATA[func_name]['calls'] += 1
        PROF_DATA[func_name]['total_time'] += elapsed_time

        # Gestion des __local_prof__ si vous l'utilisez encore
        if isinstance(result, tuple) and len(result) > 0 and isinstance(result[-1], dict) and "__local_prof__" in result[-1]:
            local_prof_data = result[-1]["__local_prof__"]
            for key, val in local_prof_data.items():
                PROF_DATA[func_name]['details'][key] = PROF_DATA[func_name]['details'].get(key, 0) + val
            result = result[:-1] # Retirer le dict de profiling du résultat
            if len(result) == 1:
                result = result[0] # Renvoyer une seule valeur si c'est le cas

        # Optionnel: print(f"Function {func_name} took {elapsed_time:.4f} seconds")
        # Dans une app web, on veut éviter les prints vers la console du serveur
        # à moins que ce soit pour du logging explicite.
        return result
    return wrapper

def normalize_city_name(city_name: str) -> str:
    return city_name.strip().lower().replace(" ", "_").replace(",", "")

def parse_dynamic_value(value_str: str, context: dict) -> int:
    """
    Interprète une chaîne pouvant contenir une variable de contexte (ex: "$nodes").
    Retourne la valeur entière.
    """
    value_str = value_str.strip()
    for key, val in context.items():
        if f"${key}" in value_str:
            # Simple remplacement pour l'instant. eval() est dangereux.
            # Pour des expressions plus complexes, il faudrait un parser plus sûr.
            try:
                # Gérer les divisions simples comme "$truck_capacity/2"
                if '/' in value_str:
                    parts = value_str.split('/')
                    var_part = parts[0].replace(f"${key}", str(val))
                    divisor = int(parts[1])
                    return int(float(var_part) / divisor)
                else:
                    value_str = value_str.replace(f"${key}", str(val))
            except ValueError:
                raise ValueError(f"Impossible d'évaluer la variable dynamique ${key} dans '{value_str}' avec la valeur {val}")

    try:
        print(f"Parsing value : {value_str}")
        return int(value_str)
    except ValueError:
        raise ValueError(f"Valeur dynamique non reconnue ou invalide : {value_str}")


def parse_interval_config(config_str: str, context: dict = None) -> tuple[int, int] | int:
    """
    Parse une configuration d'intervalle comme "1-5" ou un nombre fixe.
    Peut utiliser des variables de contexte comme "$truck_capacity".
    Retourne un tuple (min, max) ou un entier si ce n'est pas un intervalle.
    Exemple de contexte: {"truck_capacity": 10, "nodes": 100}
    """
    if context is None:
        context = {}

    config_str = str(config_str).strip() # Assurer que c'est une chaîne

    if '-' in config_str:
        parts = config_str.split('-', 1)
        try:
            min_val = parse_dynamic_value(parts[0], context)
            max_val = parse_dynamic_value(parts[1], context)
            if min_val > max_val: # Inverser si min > max
                min_val, max_val = max_val, min_val
            return max(1, min_val), max(1, max_val) # Assurer que c'est au moins 1
        except ValueError as e:
            raise ValueError(f"Format d'intervalle invalide '{config_str}': {e}")
    else:
        try:
            return max(1, parse_dynamic_value(config_str, context)) # Assurer au moins 1
        except ValueError as e:
            raise ValueError(f"Format de nombre invalide '{config_str}': {e}")
# Vous pouvez aussi mettre TRUCK_SPEED_KMH ici si c'est une constante partagée
# TRUCK_SPEED_KMH = 50