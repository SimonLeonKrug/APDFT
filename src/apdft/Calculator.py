#!/usr/bin/env python
import os
import sys
import glob
import random
import string
import warnings

import numpy as np
import jinja2 as j
import basis_set_exchange as bse
import cclib
import subprocess # nosec
import re
import getpass

import apdft

# load local orbkit
basedir = os.path.dirname(os.path.abspath(__file__))
sys.path.append('%s/../../dep/orbkit/orbkit' % basedir)
import orbkit

class Calculator(object):
	""" A concurrency-safe blocking interface for an external QM code."""

	def __init__(self, method, basisset, superimpose=False):
		self._method = method
		self._basisset = basisset
		self._superimpose = superimpose

	def get_methods(self):
		return list(self._methods.keys())

	def get_density_on_grid(self, folder, gridpoints):
		raise NotImplementedError()

	@staticmethod
	def _parse_ssh_constr(constr):
		""" Parses a connection string.

		Accepted formats:
		username:password@host+port:path/to/dir
		username@host+port:path/to/dir
		username@host+port:
		username@host:path/to/dir
		username@host
		host
		"""
		regex = r"((?P<username>[^:@]+)(:(?P<password>[^@]+))?@)?(?P<host>[^+:]+)(\+(?P<port>[^:]+))?:?(?P<path>[^:@]*)"
		matches = re.search(regex, constr)
		groups = matches.groupdict()

		if groups['port'] is None:
			groups['port'] = 22

		if groups['username'] is None:
			groups['username'] = getpass.getuser()

		if groups['path'] is '':
			groups['path'] = '.'

		return groups['username'], groups['password'], groups['host'], groups['port'], groups['path']

	@staticmethod
	def _get_tempname():
		return 'apdft-tmp-' + ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10))

	@staticmethod
	def get_grid(nuclear_numbers, coordinates, outputfolder):
		""" Returns the integration grid used by this calculator for a given set of nuclei and geometry.

		Grid weights and coordinates may be in internal units. Return value should be coords, weights. If return value is None, a default grid is used."""
		return None

	@staticmethod
	def execute(folder, remote_constr=None, remote_preload=None):
		""" Run a calculation with the input file in folder."""

		if remote_constr == None:
			p = subprocess.run('%s/run.sh' % folder, universal_newlines=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)  # nosec
			if p.returncode != 0:
				print ('E + Error running %s/run.sh:')
				for line in p.stdout.split('\n'):
					print ('E | %s' % line)
				print ('E + Run skipped.\n')
		else:
			import paramiko
			with paramiko.SSHClient() as s:
				# connect
				#s.load_system_host_keys()

				s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
				username, password, host, port, path = Calculator._parse_ssh_constr(remote_constr)

				try:
					with warnings.catch_warnings():
						warnings.simplefilter('ignore')
						s.connect(host, port, username, password)
				except paramiko.ssh_exception.NoValidConnectionsError:
					apdft.log.log('Unable to establish SSH connection.', level='error', host=host, port=port, username=username, password=password)
					return
				except:
					apdft.log.log('General SSH error.', level='error', host=host, port=port, username=username, password=password)
					return
				sftp = s.open_sftp()
				sftp.chdir(path)

				# create temporary folder
				tmpname = Calculator._get_tempname()
				sftp.mkdir(tmpname)
				sftp.chdir(tmpname)
				
				# copy files
				for fn in glob.glob('%s/*' % folder):
					sftp.put(fn, os.path.basename(fn))
				sftp.chmod('run.sh', 0o700)

				# run
				_ = s.exec_command('cd %s; cd %s' % (path, tmpname)) # nosec
				stdout = _[0]
				if stdout.channel.recv_exit_status() != 0:
					apdft.log.log('Unable to navigate on remote machine.', level='error', host=host, port=port, username=username, password=password, path="%s/%s" % (path, tmpname))
					return

				if remote_preload == None:
					remote_preload = ''
				else:
					remote_preload = '%s; ' % remote_preload
				_ = s.exec_command('%scd %s; cd %s; ./run.sh' % (remote_preload, path, tmpname)) # nosec
				stdout = _[0]
				status = stdout.channel.recv_exit_status()
				if status != 0:
					msglines = stdout.readlines() + stderr.readlines()
					apdft.log.log('Unable to execute runscript on remote machine.', level='error', host=host, port=port, username=username, password=password, path=folder, remotemsg=msglines)

				# copy back
				for fn in sftp.listdir():
					sftp.get(fn, '%s/%s' % (folder, fn))

				# clear
				s.exec_command('cd %s; rm -rf "%s"' % (path, tmpname)) # nosec


class MockCalculator(Calculator):
	_methods = {}
	@classmethod
	def get_runfile(self, coordinates, nuclear_numbers, nuclear_charges, grid):
		basedir = os.path.dirname(os.path.abspath(__file__))
		with open('%s/templates/mock-run.sh' % basedir) as fh:
			template = j.Template(fh.read())
		return template.render()


class MrccCalculator(Calculator):
	_methods = {
		'CCSD': 'ccsd',
	}

	@staticmethod
	def _parse_densityfile(densityfile):
		with open(densityfile, 'r') as fh:
			_ = np.fromfile(fh, 'i4')
			q = _[3:-1].view(np.float64)
			ccdensity = q.reshape((-1, 10))
		return ccdensity[:, 1:6]

	@staticmethod
	def density_on_grid(inputfile, grid):
		ccdensity = MrccCalculator._parse_densityfile('%s/DENSITY' % outputfolder)
		if not np.allclose(grid, ccdensity[:3]):
			raise ValueError('Trying to combine different grids.')
		return ccdensity[5]
	
	@staticmethod
	def get_grid(nuclear_numbers, coordinates, outputfolder):
		""" Obtains the integration grid from one of the MRCC output files. """
		ccdensity = MrccCalculator._parse_densityfile('%s/DENSITY' % outputfolder)
		return ccdensity[:, :3], ccdensity[:, 3]

	@staticmethod
	def _format_charges(coordinates, nuclear_numbers, nuclear_charges):
		ret = []
		for coord, Z_ref, Z_tar in zip(coordinates, nuclear_numbers, nuclear_charges):
			ret.append('%f %f %f %f' % (coord[0], coord[1], coord[2], (Z_tar - Z_ref)))
		return '\n'.join(ret)

	def get_input(self, coordinates, nuclear_numbers, nuclear_charges, grid, iscomparison=False):
		basedir = os.path.dirname(os.path.abspath(__file__))
		with open('%s/templates/mrcc.txt' % basedir) as fh:
			template = j.Template(fh.read())
		
		env_coord = GaussianCalculator._format_coordinates(nuclear_numbers, coordinates)
		env_basis = self._basisset
		env_numatoms = len(nuclear_numbers)
		env_charged = MrccCalculator._format_charges(coordinates, nuclear_numbers, nuclear_charges)
		
		return template.render(coordinates=env_coord, method=self._methods[self._method], basisset=env_basis, numatoms=env_numatoms, charges=env_charged)

	@classmethod
	def get_runfile(self, coordinates, nuclear_numbers, nuclear_charges, grid):
		basedir = os.path.dirname(os.path.abspath(__file__))
		with open('%s/templates/mrcc-run.sh' % basedir) as fh:
			template = j.Template(fh.read())
		return template.render()

	def get_density_on_grid(self, folder, gridpoints):
		return MrccCalculator.density_on_grid(folder + '/DENSITY', grid)

	@staticmethod
	def get_total_energy(folder):
		""" Returns the total energy in Hartree."""
		raise NotImplementedError()

	@staticmethod
	def get_electronic_dipole(folder, gridcoords, gridweights):
		raise NotImplementedError()

class GaussianCalculator(Calculator):
	_methods = {
		'CCSD': 'CCSD(Full,MaxCyc=100)',
		'PBE0': 'PBE1PBE',
		'PBE': 'PBEPBE',
		'HF': 'UHF',
	}

	@staticmethod
	def _format_coordinates(nuclear_numbers, coordinates):
		ret = ''
		for Z, coords in zip(nuclear_numbers, coordinates):
			ret += '%d %f %f %f\n' % (Z, coords[0], coords[1], coords[2])
		return ret[:-1]

	@staticmethod
	def _format_basisset(nuclear_charges, basisset, superimposed=False):
		res = ''
		for atomid, nuclear_charge in enumerate(nuclear_charges):
			if superimposed:
				elements = set([max(1, int(_(nuclear_charge))) for _ in (np.round, lambda _: np.round(_ + 1), lambda _: np.round(_ - 1))])
			else:
				elements = set([max(1, int(_(nuclear_charge))) for _ in (np.round,)])
			output = bse.get_basis(basisset, elements=list(elements), fmt='gaussian94')

			res += '%d 0\n' % (atomid + 1)
			skipnext = False
			for line in output.split('\n'):
				if line.startswith('!'):
					skipnext = False
					continue
				if len(line.strip()) == 0 or line.strip() == '****':
					skipnext = True
					continue
				if skipnext:
					skipnext = False
					continue
				res += line + '\n'
			res += '****\n'

		return res.strip()

	@staticmethod
	def _format_nuclear(nuclear_charges):
		return '\n'.join(['%d Nuc %f' % (_[0] + 1, _[1]) for _ in enumerate(nuclear_charges)])

	@staticmethod
	def density_on_grid(inputfile, grid):
		orbkit.options.quiet = True
		orbkit.grid.x = grid[:, 0]*1.88973
		orbkit.grid.y = grid[:, 1]*1.88973
		orbkit.grid.z = grid[:, 2]*1.88973
		orbkit.grid.is_initialized = True

		try:
			qc = orbkit.read.main_read(inputfile, itype='gaussian.fchk')
			rho = orbkit.core.rho_compute(qc, numproc=1)
		except:
			apdft.log.log('Unable to read fchk file with orbkit.', level='error', filename=inputfile)
			return grid[:, 0] * 0
		return rho

	def get_input(self, coordinates, nuclear_numbers, nuclear_charges, grid, iscomparison=False):
		basedir = os.path.dirname(os.path.abspath(__file__))
		with open('%s/templates/gaussian.txt' % basedir) as fh:
			template = j.Template(fh.read())

		env_coord = GaussianCalculator._format_coordinates(nuclear_numbers, coordinates)
		env_basis = GaussianCalculator._format_basisset(nuclear_charges, self._basisset, self._superimpose)
		env_nuc = GaussianCalculator._format_nuclear(nuclear_charges)
		env_molcharge = int(np.sum(nuclear_charges) - np.sum(nuclear_numbers))
		return template.render(coordinates=env_coord, method=self._methods[self._method], basisset=env_basis, nuclearcharges=env_nuc, moleculecharge=env_molcharge)

	@classmethod
	def get_runfile(self, coordinates, nuclear_numbers, nuclear_charges, grid):
		basedir = os.path.dirname(os.path.abspath(__file__))
		with open('%s/templates/gaussian-run.sh' % basedir) as fh:
			template = j.Template(fh.read())
		return template.render()

	def get_density_on_grid(self, folder, gridpoints):
		return GaussianCalculator.density_on_grid(folder + '/run.fchk', gridpoints)

	@staticmethod
	def get_total_energy(folder):
		""" Returns the total energy in Hartree."""
		logfile = '%s/run.log' % folder
		try:
			data = cclib.io.ccread(logfile)
		except:
			apdft.log.log('Unable to read energy from log file.', filename=logfile, level='error')
			return 0
		energy = None
		energy = data.scfenergies
		try:
			energy = data.ccenergies
		except AttributeError:
			pass
		return energy / 27.21138602

	@staticmethod
	def get_electronic_dipole(folder, gridcoords, gridweights):
		""" Returns the electronic dipole moment."""
		#data = cclib.io.ccread('%s/run.log' % folder)
		#return data.moments[1]

		rho = GaussianCalculator.density_on_grid('%s/run.fchk' % folder, gridcoords)
		return -np.sum(gridcoords.T * rho * gridweights, axis=1)

