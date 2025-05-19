import json

def merge_unified_files_no_overwrite(file1, file2, output_file="merged_inventory.json"):
    # Carrega os dois arquivos JSON
    with open(file1, 'r', encoding='utf-8') as f1:
        data1 = json.load(f1)

    with open(file2, 'r', encoding='utf-8') as f2:
        data2 = json.load(f2)

    # Cria estrutura base do JSON unificado
    merged = {"servers": {}}

    for source in [data1, data2]:
        for server_key, server_data in source.get("servers", {}).items():
            if server_key not in merged["servers"]:
                merged["servers"][server_key] = {"recorders": {}}

            # Adiciona os recorders sem sobrescrever existentes
            for recorder_name, recorder_data in server_data.get("recorders", {}).items():
                if recorder_name not in merged["servers"][server_key]["recorders"]:
                    merged["servers"][server_key]["recorders"][recorder_name] = recorder_data
                else:
                    # Se já existir, cria uma nova chave com sufixo numérico incremental
                    suffix = 1
                    new_name = f"{recorder_name}_{suffix}"
                    while new_name in merged["servers"][server_key]["recorders"]:
                        suffix += 1
                        new_name = f"{recorder_name}_{suffix}"
                    merged["servers"][server_key]["recorders"][new_name] = recorder_data

    # Salva o resultado
    with open(output_file, 'w', encoding='utf-8') as fout:
        json.dump(merged, fout, indent=2, ensure_ascii=False)

    print(f"Arquivo mesclado salvo em '{output_file}' (sem sobrescrever recorders)")

# Exemplo de uso:
merge_unified_files_no_overwrite("unified_inventory_server1.json", "unified_inventory_server2.json")
