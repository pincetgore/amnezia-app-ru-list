import pytest
import yaml
import ipaddress
from ipaddress import IPv4Network
from output.formatter import aggregate_networks


def test_aggregate_cidrs_removes_subnets():
    """Проверяет, что мелкие подсети поглощаются более крупными."""
    ips = [
        IPv4Network("10.0.0.0/8"),
        IPv4Network("10.1.0.0/16"),   # Должно поглотиться первой строкой
        IPv4Network("192.168.1.1/32")
    ]
    result = aggregate_networks(ips)
    result_strs = [str(net) for net in result]
    
    assert "10.0.0.0/8" in result_strs
    assert "10.1.0.0/16" not in result_strs, "Вложенная подсеть 10.1.0.0/16 не была удалена!"
    assert "192.168.1.1/32" in result_strs

def test_config_yaml_is_valid():
    """Проверяет, что рабочий config.yaml имеет правильную структуру."""
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    assert isinstance(config, dict), "Конфиг должен быть словарем"
    assert "services" in config, "Конфиг должен содержать ключ 'services'"
    services = config["services"]
    assert isinstance(services, list), "services должен быть списком"
    
    for entry in services:
        assert "name" in entry, f"Отсутствует 'name' в записи: {entry}"
        assert "asn" in entry or "domains" in entry or "ip_ranges" in entry, f"Запись {entry['name']} должна иметь asn, domains или ip_ranges"
        
        if "asn" in entry and entry["asn"]:
            assert isinstance(entry["asn"], list), f"ASN в {entry['name']} должен быть списком"
            for asn in entry["asn"]:
                assert isinstance(asn, int), f"ASN {asn} должен быть числом"

def test_domains_format():
    """Проверяет отсутствие опечаток (например http://) в доменах."""
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    services = config.get("services", [])
    for entry in services:
        for domain in entry.get("domains", []):
            assert not domain.startswith("http"), f"Домен не должен содержать протокол: {domain}"
            assert not domain.endswith("/"), f"Домен не должен заканчиваться на слеш: {domain}"
            assert " " not in domain, f"Домен не должен содержать пробелы: '{domain}'"
            assert not domain.startswith("*"), f"Wildcard-домены (*.domain) не поддерживаются: {domain}"

def test_no_duplicate_domains():
    """Проверяет отсутствие дубликатов доменов во всем config.yaml."""
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    seen_domains = {}
    duplicates = []
    
    for service in config.get("services", []):
        service_name = service.get("name", "Unknown")
        for domain in service.get("domains") or []:
            if domain in seen_domains:
                duplicates.append(f"{domain} (в '{service_name}' и '{seen_domains[domain]}')")
            else:
                seen_domains[domain] = service_name
                
    assert not duplicates, "Найдены дублирующиеся домены:\n" + "\n".join(duplicates)

def test_no_duplicate_asns():
    """Проверяет отсутствие дубликатов ASN во всем config.yaml."""
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    seen_asns = {}
    duplicates = []
    
    for service in config.get("services", []):
        service_name = service.get("name", "Unknown")
        for asn in service.get("asn") or []:
            if asn in seen_asns:
                duplicates.append(f"AS{asn} (в '{service_name}' и '{seen_asns[asn]}')")
            else:
                seen_asns[asn] = service_name
                
    assert not duplicates, "Найдены дублирующиеся ASN:\n" + "\n".join(duplicates)

def test_no_duplicate_ip_ranges():
    """Проверяет отсутствие точных дубликатов ip_ranges во всем config.yaml."""
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    seen_ips = {}
    duplicates = []
    
    for service in config.get("services", []):
        service_name = service.get("name", "Unknown")
        for ip in service.get("ip_ranges") or []:
            if ip in seen_ips:
                duplicates.append(f"{ip} (в '{service_name}' и '{seen_ips[ip]}')")
            else:
                seen_ips[ip] = service_name
                
    assert not duplicates, "Найдены дублирующиеся ip_ranges:\n" + "\n".join(duplicates)