#!/usr/bin/python3
import sys

sys.path = ['../'] + sys.path

import unittest
import getData


class TestgetData(unittest.TestCase):
  def test_getChapters(self):
    expected = [
        f"http://www.mangareader.net/bleach/{i}"
        for i in range(1, 687)]
    found_Bleach = getData.getChapters('Bleach')
    found_bleach = getData.getChapters('bleach')

    self.assertEqual(expected, found_Bleach)
    self.assertEqual(expected, found_bleach)

  def test_getPages(self):
    # Should be 57 pages and should allow leading 0s
    self.assertEqual(getData.getPages('bleach', '1'), 57)
    self.assertEqual(getData.getPages('bleach', '01'), 57)

  def test_getImage(self):
    image_1 = getData.getImage('bleach', '1', '1')
    image_2 = getData.getImage('bleach', '001', '01')
    self.assertIsNot(image_1, None)
    self.assertEqual(image_1, image_2)

  def test_alttitle(self):
    expected = [
        f"http://www.mangareader.net/toukyou-kushu/{i}"
        for i in range(1, 145)]
    found_ghoul = getData.getChapters('Tokyo Ghoul')
    self.assertEqual(expected, found_ghoul)
    self.assertEqual(getData.getPages('Tokyo Ghoul', '1'), 40)
    image_1 = getData.getImage('Tokyo Ghoul', '1', '1')
    self.assertIsNot(image_1, None)

if __name__ == '__main__':
    unittest.main()
