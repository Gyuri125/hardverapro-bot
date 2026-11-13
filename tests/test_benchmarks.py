"""PassMark lekérdezés és linkgenerálás tesztjei (hálózat nélkül)."""

from dealradar.benchmarks import Benchmarks, cpu_queries, gpu_queries
from dealradar.links import cpu_manufacturer_url, specs_query, specs_url

CPU_HTML = """
<html><head><title>Intel Core i7-14700HX Benchmark</title></head>
<body><h1>Intel Core i7-14700HX</h1>
<script>
  stripLines: [{ value: 36314, label: "Average CPU Mark: 36,314" }]
</script></body></html>
"""

GPU_HTML = """
<html><head><title>PassMark - GeForce RTX 4060 Laptop GPU</title></head>
<body><h1>GeForce RTX 4060 Laptop GPU</h1>
<script>
  stripLines: [{ value: 17306, label: "Average G3D Mark: 17,306" }]
</script></body></html>
"""


class StubFetcher:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def get(self, url, use_cache=False):
        self.calls.append(url)
        for needle, html in self.mapping.items():
            if needle in url:
                if html is None:
                    from dealradar.fetch import FetchError

                    raise FetchError("HTTP 404")
                return html
        from dealradar.fetch import FetchError

        raise FetchError("HTTP 404")


def test_cpu_queries():
    assert cpu_queries("i7-14700HX") == ["Intel Core i7-14700HX"]
    assert cpu_queries("ultra 7 155H") == ["Intel Core Ultra 7 155H"]
    assert cpu_queries("ryzen 7 7840HS")[0] == "AMD Ryzen 7 7840HS"
    assert cpu_queries("valami") == ["valami"]


def test_gpu_queries_prefers_laptop_variant():
    queries = gpu_queries("rtx 4060")
    assert queries[0] == "GeForce RTX 4060 Laptop GPU"
    assert queries[1] == "GeForce RTX 4060"


def test_cpu_lookup_parses_score():
    fetcher = StubFetcher({"cpu.php": CPU_HTML})
    bench = Benchmarks(fetcher)
    result = bench.cpu("i7-14700HX")
    assert result is not None
    assert result.score == 36314
    assert result.name == "Intel Core i7-14700HX"
    assert result.kind == "cpu"


def test_gpu_lookup_falls_back_to_desktop_variant():
    fetcher = StubFetcher({"Laptop+GPU": None, "gpu.php": GPU_HTML})
    bench = Benchmarks(fetcher)
    result = bench.gpu("rtx 4060")
    assert result is not None
    assert result.score == 17306


def test_missing_benchmark_is_none():
    fetcher = StubFetcher({})
    bench = Benchmarks(fetcher)
    assert bench.cpu("i7-9999H") is None
    assert bench.gpu("rtx 9999") is None


def test_lookup_cache_avoids_refetch():
    fetcher = StubFetcher({"cpu.php": CPU_HTML})
    bench = Benchmarks(fetcher)
    bench.cpu("i7-14700HX")
    bench.cpu("i7-14700HX")
    assert len(fetcher.calls) == 1


def test_max_lookups_is_respected():
    fetcher = StubFetcher({"cpu.php": CPU_HTML})
    bench = Benchmarks(fetcher, max_lookups=0)
    assert bench.cpu("i7-14700HX") is None


def test_manufacturer_urls():
    assert "intel.com" in cpu_manufacturer_url("i7-14700HX")
    assert "intel.com" in cpu_manufacturer_url("ultra 7 155H")
    assert "amd.com" in cpu_manufacturer_url("ryzen 7 7840HS")
    assert cpu_manufacturer_url(None) is None
    assert cpu_manufacturer_url("apple m3") is None


def test_specs_query_strips_noise():
    query = specs_query("Eladó Lenovo Legion 5 15ACH6H gamer laptop, magyar billentyűzet, ÚJ")
    assert "Lenovo" in query
    assert "Legion" in query
    assert "15ACH6H" in query
    assert "gamer" not in query.lower()
    assert "magyar" not in query.lower()


def test_specs_url_is_google_search():
    url = specs_url("Lenovo Legion 5 15ACH6H")
    assert url.startswith("https://www.google.com/search?q=")
    assert "Legion" in url
