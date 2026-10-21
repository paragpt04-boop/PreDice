import math
import random
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.market import Candle, normalize_symbol
from app.predictor import forecast, walk_forward

class PredictionTests(unittest.TestCase):
    @staticmethod
    def candles():
        rng=random.Random(42)
        arr=[]
        price=100.
        for i in range(600):
            step=.001*math.sin(i/31) + .005*(rng.random()-.5)
            newprice=price*(1+step)
            arr.append(Candle(i*60000,price,max(price,newprice),min(price,newprice),
                              newprice, 10+rng.random()*100))
            price=newprice
        return arr

    def test_symbols(self):
        self.assertEqual(normalize_symbol("btc"),"BTCUSDT")
        self.assertEqual(normalize_symbol("https://www.bitunix.com/contract-trade/BTCUSDT"),"BTCUSDT")
        with self.assertRaises(ValueError): normalize_symbol("<script>")

    def test_no_future_leak(self):
        candles=self.candles()
        a=forecast(candles[:500],5)
        b=forecast(candles,5,asof=499)
        self.assertIsNotNone(a)
        self.assertAlmostEqual(a.expected_pct,b.expected_pct,places=10)
        self.assertAlmostEqual(a.up_vote,b.up_vote,places=10)

    def test_walkforward(self):
        result=walk_forward(self.candles(),5)
        self.assertGreater(result["evaluations"],0)
        self.assertGreaterEqual(result["accuracy_pct"],0)
        self.assertLessEqual(result["accuracy_pct"],100)

if __name__=="__main__": unittest.main()
