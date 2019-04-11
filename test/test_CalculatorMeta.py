#!/usr/bin/env python
import pytest
import numpy as np
import mqm.Calculator as mqmc

def test_force_init():
	with pytest.raises(NotImplementedError):
		mqmc.Calculator()

def test_horton_has_methods():
	assert 'HF' in mqmc.HortonCalculator._methods.keys()

def test_horton():
	return 
	c = mqmc.HortonCalculator()
	coordinates = np.array([[0., 0., 0.], [0., 0., 1.]])
	nuclear_numbers = np.array([1, 1])
	nuclear_charges = np.array([1., 1.])
	grid = None
	method = 'HF'
	basisset = 'STO-3g'
	c.evaluate(coordinates, nuclear_numbers, nuclear_charges, grid, basisset, method)

def test_gaussian_input():
	c = mqmc.GaussianCalculator()
	coordinates = np.array([[0., 0., 0.], [0., 0., 1.]])
	nuclear_numbers = np.array([1, 1])
	nuclear_charges = np.array([2., 2.])
	grid = None
	method = 'CCSD'
	basisset = 'STO-3g'
	c._get_input(coordinates, nuclear_numbers, nuclear_charges, grid, basisset, method)
