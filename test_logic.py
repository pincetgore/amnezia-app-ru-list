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
        assert "asn" in entry or "domains" in entry, f"Запись {entry['name']} должна иметь asn или domains"
        
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